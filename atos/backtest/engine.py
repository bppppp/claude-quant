"""回测引擎 - 多标的组合"""
import logging
import uuid
import warnings
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("atos")


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: pd.DataFrame
    daily_returns: pd.Series
    metrics: dict
    regime_history: Optional[pd.DataFrame] = None


class BacktestEngine:
    """多标的组合回测引擎"""

    def __init__(self, config):
        self.config = config
        self.positions: dict = {}
        self.cash = config.initial_capital
        self.trades = []
        self.equity_history = []
        self.cooldown = None
        self.drawdown_tracker = None
        self.money_mgr = None
        self.regime_history = []

    def run(self,
            market_df: pd.DataFrame,
            stock_data: dict = None,
            benchmark_df: pd.DataFrame = None,
            test_only_period: tuple = None) -> "BacktestResult":
        """运行回测

        Args:
            market_df: 大盘指数数据（已含指标）
            stock_data: 个股数据字典 {symbol: df}
            benchmark_df: 基准（备用）
            test_only_period: (start, end) 限制回测区间
        """
        # 1. 大盘状态识别
        from atos.regime import detect_full_regime
        regime_df = detect_full_regime(market_df, self.config)

        # 2. 初始化管理器
        from atos.risk import CooldownManager, DrawdownTracker, MoneyManager
        self.cooldown = CooldownManager()
        self.drawdown_tracker = DrawdownTracker()
        self.money_mgr = MoneyManager(self.config.initial_capital)

        # 2.5 初始化 persistent selector（保持因子缓存跨日复用）
        self._persistent_selector = None
        if stock_data and len(stock_data) > 0:
            from atos.selection import StockSelector
            self._persistent_selector = StockSelector(self.config)

        # 2.6 缓存 stock_data 用于涨跌停/停牌/退市检查
        self._stock_df_cache = stock_data if stock_data else {}

        # 2.7 跨日复用的信号缓存（首次为每只股票计算整个时间序列）
        self._signal_cache = {}

        # 2.8 events 记录（全部信号触发，含 triggered/executed/skipped/swallowed）
        self.all_events = []

        # 2.9 signal_attribution（每个信号 PnL 贡献，回测结束后统计）
        self._signal_trades = []  # [(signal_type, pnl_amt, pnl_pct), ...]
        self._open_trade_signals = {}  # trade_id -> {signal_type: True}

        # 2.10 spec §6.1 自适应跟踪器（持仓周期/开仓阈值/market_breadth）
        from atos.risk.adaptive import AdaptiveTracker
        self.adaptive = AdaptiveTracker(self.config, market_df=market_df)

        # 2.11 ATOS2 v1：回撤阶梯状态
        self._drawdown_step_active = 0  # 当前激活的回撤阶梯（0=无, 1=5%, 2=10%, 3=15%）
        self._drawdown_step_until = None  # 阶梯到期日

        # 3. 处理回测区间
        # 留出 warmup（至少 60 日用于计算指标/状态；数据不足时用 0）
        start_idx = min(60, max(0, len(market_df) - 30))
        end_idx = len(market_df)
        if test_only_period is not None:
            period_start, period_end = test_only_period
            try:
                start_idx = market_df.index.get_loc(pd.Timestamp(period_start))
            except KeyError:
                start_idx = 60
            try:
                end_idx = market_df.index.get_loc(pd.Timestamp(period_end)) + 1
            except KeyError:
                end_idx = len(market_df)

        # 4. 状态切换跟踪
        prev_state = None
        # 4.5 待执行订单（key=date, value=list of (symbol, price, regime)）
        self._pending_orders = {}
        # 4.6 待执行卖出（key=date, value=list of (symbol, ratio, reason)）—— T+1 开盘成交
        self._pending_sell_orders = {}

        # 5. 逐日循环
        for i in range(start_idx, end_idx):
            date = market_df.index[i]

            # 5.0 先执行前一日产生的 pending orders（T+1 结算）
            if date in self._pending_orders:
                for symbol, price, regime in self._pending_orders[date]:
                    if symbol not in self.positions:
                        self._execute_buy_on_execution(symbol, price, regime, date)
                del self._pending_orders[date]

            # 5.0a 执行前一日产生的 pending sell orders（T+1 开盘成交）
            if date in self._pending_sell_orders:
                for symbol, ratio, reason in self._pending_sell_orders[date]:
                    self._execute_sell_on_execution(symbol, date, ratio, reason, market_df, stock_data)
                del self._pending_sell_orders[date]

            try:
                effective_state = regime_df.loc[date, "effective_state"]
                target_position_cap = float(regime_df.loc[date, "target_position"])
            except Exception:
                continue

            # 记录状态切换
            if prev_state is not None and effective_state != prev_state:
                self.cooldown.record_regime_switch(prev_state, effective_state, date)
            prev_state = effective_state

            # 当日 OHLC
            row = market_df.loc[date]
            current_price = float(row["close"])
            current_high = float(row["high"])
            current_atr = float(row["ATR"]) if "ATR" in row.index and not pd.isna(row["ATR"]) else current_price * 0.02

            # 处理卖出 —— 决策 T，登记 pending，T+1 开盘成交（修复：符合 spec §4.1/§4.2 的"次日开盘"要求）
            self._process_sells(date, current_prices_by_sym=self._gather_position_prices(date, market_df, stock_data),
                                regime=effective_state, market_atr=current_atr, market_high=current_high)

            # 处理买入（仅当不是 CRASH）—— 决策 T，执行 T+1
            # ATOS2 v1：回撤阶梯 3 = 空仓
            effective_target_cap = self._get_position_cap_with_step(target_position_cap)
            if effective_state != "CRASH" and effective_target_cap > 0:
                self._process_buys(date, current_price, effective_state, effective_target_cap,
                                    market_df, stock_data)

            # 记录净值
            self._record_equity(date, market_df, stock_data, effective_state)

            # 记录状态
            self.regime_history.append({
                "date": date,
                "state": effective_state,
                "target_position": target_position_cap,
            })

        # 处理背测结束时的 pending orders（不执行，丢弃）
        self._pending_orders = {}
        self._pending_sell_orders = {}

        return self._build_result(regime_df)

    def _gather_position_prices(self, date, market_df, stock_data) -> dict:
        """获取所有持仓股票的价格（修复：日期不匹配时用最近前一日的价）"""
        prices = {}
        for symbol in self.positions:
            if stock_data and symbol in stock_data:
                df = stock_data[symbol]
                try:
                    if date in df.index:
                        prices[symbol] = float(df.loc[date, "close"])
                    else:
                        # 修复：用最近的前一个交易日价（ffill）
                        valid = df.index[df.index <= date]
                        if len(valid) > 0:
                            prices[symbol] = float(df.loc[valid[-1], "close"])
                except Exception:
                    pass
            if symbol not in prices:
                # 回退到 market_df
                try:
                    prices[symbol] = float(market_df.loc[date, "close"])
                except Exception:
                    pass
        return prices

    def _get_atr_for(self, symbol, date, market_df, stock_data) -> float:
        """获取持仓股的当前 ATR（日期不匹配时用最近前一日的 ATR）"""
        if stock_data and symbol in stock_data:
            try:
                df = stock_data[symbol]
                if "ATR" not in df.columns:
                    return 0.0
                if date in df.index:
                    atr = df.loc[date, "ATR"]
                else:
                    valid = df.index[df.index <= date]
                    if len(valid) == 0:
                        return 0.0
                    atr = df.loc[valid[-1], "ATR"]
                if pd.isna(atr):
                    return float(df.iloc[-1]["close"]) * 0.02 if "close" in df.columns else 0.0
                return float(atr)
            except Exception:
                pass
        try:
            atr = market_df.loc[date, "ATR"]
            if pd.isna(atr):
                return float(market_df.loc[date, "close"]) * 0.02
            return float(atr)
        except Exception:
            return 0.0

    def _process_sells(self, date, current_prices_by_sym, regime, market_atr, market_high):
        """处理所有持仓的卖出检查

        修复：T 日决策信号 → 登记 pending sell order → T+1 开盘成交
        符合 spec §4.1 (CRASH 次日开盘清仓) + §4.2 (移动止盈次日开盘) 的要求。
        T+1 涨跌停/停牌在 _execute_sell_on_execution 中再检查。
        """
        from atos.risk import check_exit

        for symbol in list(self.positions.keys()):
            if symbol not in current_prices_by_sym:
                continue
            pos = self.positions[symbol]
            current_price = current_prices_by_sym[symbol]
            current_atr = self._get_atr_for(symbol, date, None, None)
            if current_atr <= 0:
                current_atr = current_price * 0.02

            # 单标的模式下用市场 high 作为 high 价
            if symbol == self.config.symbol:
                ch = market_high
            else:
                ch = current_price

            should_sell, ratio, reason = check_exit(
                pos, current_price, current_atr, date, regime, self.config,
                current_high=ch,
                adaptive_holding_period=self.adaptive.get_adaptive_holding_period(regime),
            )

            if should_sell and ratio > 0:
                # T 日：登记 pending sell order，T+1 开盘成交
                next_day = date + pd.tseries.offsets.BDay(1)
                if next_day not in self._pending_sell_orders:
                    self._pending_sell_orders[next_day] = []
                self._pending_sell_orders[next_day].append((symbol, ratio, reason))

    def _get_stock_row(self, symbol, date):
        """获取指定日期的股票原始数据行"""
        # 优先用 self._stock_df_cache（如果存在）
        if hasattr(self, '_stock_df_cache') and symbol in self._stock_df_cache:
            df = self._stock_df_cache[symbol]
            if date in df.index:
                return df.loc[date]
        return None

    def _process_buys(self, date, current_price, regime, target_position_cap,
                       market_df, stock_data):
        """处理买入"""
        # 单标的模式：用 sig_final 列（已在回测主循环外准备好）
        # 多标的模式：选股 + 买入
        if stock_data is None or len(stock_data) == 0:
            # 单标的模式
            symbol = self.config.symbol
            if "sig_final" in market_df.columns:
                try:
                    sig = market_df.loc[date, "sig_final"]
                except Exception:
                    sig = 0
                if sig == 1 and symbol not in self.positions:
                    # 冷却检查
                    can, _ = self.cooldown.can_buy(symbol, date, regime)
                    if can:
                        # T+1 开盘价成交
                        next_day = date + pd.tseries.offsets.BDay(1)
                        try:
                            next_open = float(market_df.loc[next_day, "open"])
                        except Exception:
                            next_open = current_price
                        self._execute_buy(next_day, symbol, next_open, regime)
        else:
            # 多标的模式：选股
            if isinstance(self.config.top_n_stocks, dict):
                target_n = self.config.top_n_stocks.get(regime, 0)
            else:
                target_n = self.config.top_n_stocks
            if target_n <= 0:
                return
            if len(self.positions) >= target_n:
                return

            # 严格按策略文档 §8.1 "主信号+辅信号分级" 排序
            # 规则 1: 主信号触发 + 状态对应 → 立即候选
            # 规则 2: 仅辅信号 → 需 ≥2 个辅信号同时触发
            # 规则 3: 主辅混合 → 加权得分 (主×2 + 辅×1) 排序
            # 规则 4: 同分 → 优先主信号
            #
            # 主信号与辅信号定义（按状态）：
            #   BULL:        主=[sig_ma_macd, sig_dc_break]  辅=[sig_ma_conv]
            #   SIDEWAYS:    主=[sig_kdj_rsi]                辅=[sig_boll_vol]
            #   BEAR:        主=[sig_macd_div]                辅=[sig_boll_vol]
            #   CHOPPY_BEAR: 专用反弹捕捉（非标准 6 信号）
            #   CRASH: 禁止买入

            # ATOS11 v1: BULL 用趋势信号，其余用均值回归
            # - BULL: 趋势跟随（ma_macd 金叉 + dc_break 突破 + pullback_buy 回调买入）
            # - SIDEWAYS/BEAR/CHOPPY_BEAR: 均值回归（核心策略）
            PRIMARY_SIGNALS = {
                "BULL": ["sig_mean_reversion", "sig_ma_macd", "sig_dc_break", "sig_pullback_buy"],
                "SIDEWAYS": ["sig_mean_reversion", "sig_kdj_rsi", "sig_range_osc"],
                "BEAR": ["sig_mean_reversion", "sig_macd_div", "sig_oversold_bounce"],
                "CHOPPY_BEAR": ["sig_mean_reversion", "sig_macd_div", "sig_oversold_bounce"],
            }
            SECONDARY_SIGNALS = {
                "BULL": ["sig_ma_conv", "sig_kdj_rsi"],
                "SIDEWAYS": ["sig_boll_vol", "sig_oversold_bounce"],
                "BEAR": ["sig_boll_vol", "sig_range_osc"],
                "CHOPPY_BEAR": ["sig_boll_vol", "sig_range_osc"],
            }

            primary_cols = PRIMARY_SIGNALS.get(regime, [])
            secondary_cols = SECONDARY_SIGNALS.get(regime, [])

            if not primary_cols and not secondary_cols:
                return  # CRASH / 未知状态 不买入

            # 跨日复用的信号缓存：首次为每只股票计算整个时间序列，后续日期直接查表
            if not hasattr(self, '_signal_cache') or self._signal_cache is None:
                self._signal_cache = {}

            def _get_signal_row(symbol, df, regime):
                """获取指定股票在指定 regime 下的信号 DataFrame（首次计算后缓存）"""
                key = (symbol, regime)
                if key not in self._signal_cache:
                    from atos.signals.entry import generate_buy_signals as gen_signals
                    self._signal_cache[key] = gen_signals(df, regime, config=self.config)
                return self._signal_cache[key]

            # 计算每只股票的信号优先级得分
            # spec §6.1 自适应开仓阈值
            adaptive_threshold = self.adaptive.get_adaptive_open_threshold(regime)
            max_score = (len(primary_cols) * 2 + len(secondary_cols))
            adaptive_threshold_normalized = (
                adaptive_threshold * max_score if max_score > 0 else 0
            )
            candidates_scored = []
            for symbol, df in stock_data.items():
                if symbol in self.positions:
                    continue
                try:
                    if date not in df.index:
                        continue
                    sigs = _get_signal_row(symbol, df, regime)
                    if date not in sigs.index:
                        continue
                    row = sigs.loc[date]
                    primary_score = sum(int(row[c]) for c in primary_cols if c in sigs.columns)
                    secondary_score = sum(int(row[c]) for c in secondary_cols if c in sigs.columns)
                    weighted = primary_score * 2 + secondary_score * 1
                    primary_count = primary_score
                    secondary_count = secondary_score
                    # ATOS9 v5: mean_reversion 触发 = 直接候选（不再被 open_threshold 拦截）
                    mr_triggered = ("sig_mean_reversion" in sigs.columns
                                    and int(row.get("sig_mean_reversion", 0)) == 1)
                    if mr_triggered:
                        weighted += 100  # 强加权确保入选
                    if weighted == 0:
                        continue
                    # spec §6.1 自适应阈值过滤（mean_reversion 触发时跳过）
                    if not mr_triggered and weighted < adaptive_threshold_normalized:
                        continue
                    # 规则 2: 仅辅信号需 ≥2 个辅信号才买入（mean_reversion 触发时跳过）
                    if not mr_triggered and primary_count == 0 and secondary_count < 2:
                        continue
                    # ATOS9 v5: 按 RSI(6) 排序（最超卖优先）
                    rsi6 = float(df.loc[date, "RSI6"]) if "RSI6" in df.columns else 50.0
                    candidates_scored.append({
                        "symbol": symbol,
                        "weighted": weighted,
                        "primary_count": primary_count,
                        "secondary_count": secondary_count,
                        "close": float(df.loc[date, "close"]) if "close" in df.columns else 0,
                        "rsi6": rsi6,
                        "mr_triggered": mr_triggered,
                    })
                except Exception as e:
                    logger.debug(f"Signal calc fail {symbol} @ {date}: {e}")
                    continue

            # ATOS9 v5: 排序 - mean_reversion 触发的按 RSI(6) 升序（最超卖优先），其他按 weighted
            # ATOS10 debug: 每 60 天打印一次统计
            if date.day == 1 and date.month % 3 == 0:
                mr_count = sum(1 for x in candidates_scored if x.get("mr_triggered"))
                logger.info(f"DEBUG {date}: {len(stock_data)} stocks, {len(candidates_scored)} passed, {mr_count} mr_triggered, target_n={target_n}")
            candidates_scored.sort(key=lambda x: (
                0 if x["mr_triggered"] else 1,  # mean_reversion 触发优先
                x["rsi6"] if x["mr_triggered"] else 999,  # 同组内按 RSI 升序
                -x["weighted"],
            ))

            n_to_buy = target_n - len(self.positions)
            for cand in candidates_scored[:n_to_buy]:
                symbol = cand["symbol"]
                sym_price = cand["close"]
                if sym_price <= 0:
                    continue

                can, _ = self.cooldown.can_buy(symbol, date, regime)
                if not can:
                    continue

                # T+1 开盘价成交
                next_day = date + pd.tseries.offsets.BDay(1)
                try:
                    if symbol == self.config.symbol or symbol not in stock_data:
                        next_open = float(market_df.loc[next_day, "open"])
                    else:
                        next_open = float(stock_data[symbol].loc[next_day, "open"])
                except Exception:
                    next_open = sym_price

                self._execute_buy(next_day, symbol, next_open, regime)

    def _execute_buy(self, date, symbol, price, regime):
        """登记买入订单（T+1 开盘价成交）

        date 参数 = 实际执行日 = T+1（决策日 +1 交易日）
        price 参数 = T+1 开盘价
        regime 参数 = 决策时的状态

        本方法只登记 pending order + 记 trades，**不**扣现金 / **不**创建 position。
        实际扣款和创建 position 在 T+1 主循环开头由 _execute_buy_on_execution 完成。
        修复了原版"决策日即扣款"的 bug。

        ATOS2 v1：凯利公式仓位调整
        """
        # 检查现金是否足够
        from atos.risk import Position

        if isinstance(self.config.top_n_stocks, dict):
            target_n = self.config.top_n_stocks.get(regime, 1)
        else:
            target_n = self.config.top_n_stocks if self.config.top_n_stocks > 0 else 1
        target_ratio = self.config.base_position.get(regime, 0.5)
        single_cap = self.config.effective_single_cap(regime)

        # ATOS2 v1 + v2：凯利公式 + 自适应 Kelly 乘数
        kelly_mult = getattr(self.config, "kelly_multiplier", 0.0)
        if kelly_mult > 0 and hasattr(self, "adaptive") and self.adaptive is not None:
            # ATOS2 v2：自适应 Kelly（随胜率缩放）
            kelly_mult = self.adaptive.get_adaptive_kelly_multiplier()
            recent_trades = list(self.adaptive._recent_trades)
            if len(recent_trades) >= 10:
                wins = [t["pnl_pct"] for t in recent_trades if t["pnl_pct"] > 0]
                losses = [abs(t["pnl_pct"]) for t in recent_trades if t["pnl_pct"] <= 0]
                win_rate = len(wins) / len(recent_trades)
                avg_win = sum(wins) / len(wins) if wins else 0.02
                avg_loss = sum(losses) / len(losses) if losses else 0.02
                # half-kelly × 自适应乘数
                kelly_pct = max(0, win_rate - (1 - win_rate) * avg_loss / (avg_win + 1e-9)) * kelly_mult
                target_ratio = min(target_ratio, kelly_pct)

        target_value = self.cash * min(target_ratio, single_cap)

        shares = int(target_value / price / 100) * 100
        if shares == 0:
            return

        cost = self._calc_buy_cost(shares, price)
        if cost > self.cash * 0.95:
            affordable = int(self.cash * 0.95 / self._calc_buy_unit_cost(price) / 100) * 100
            if affordable < 100:
                return
            shares = affordable
            cost = self._calc_buy_cost(shares, price)

        # T 日：记录 trade + 登记 pending order
        trade_id = f"{symbol}_{date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        self.trades.append({
            "trade_id": trade_id,
            "date": date, "action": "BUY", "symbol": symbol,
            "price": price, "shares": shares, "regime": regime,
        })
        # pending order 等待 T+1 执行
        if date not in self._pending_orders:
            self._pending_orders[date] = []
        self._pending_orders[date].append((symbol, price, regime))

    def _execute_buy_on_execution(self, symbol, price, regime, execution_date):
        """T+1 实际执行：扣现金 + 创建 position（修复：检查涨跌停/停牌/退市）"""
        from atos.risk import Position

        # 涨跌停/停牌/退市检查
        stock_data_row = self._get_stock_row(symbol, execution_date)
        if stock_data_row is not None:
            # 涨停日：无法买入
            if "is_limit_up" in stock_data_row.index:
                try:
                    if bool(stock_data_row["is_limit_up"]):
                        return  # 涨停日买入被挡
                except Exception:
                    pass
            # 停牌：无法买入
            if "volume" in stock_data_row.index:
                try:
                    if float(stock_data_row["volume"]) == 0:
                        return
                except Exception:
                    pass
            # 退市：无法买入（注意：v2 数据 delist_date 存为字符串 '-' 表示未退市，
            #         必须先检查类型/字符串占位符，否则 pd.notna('-')==True 会误判）
            if "delist_date" in stock_data_row.index:
                try:
                    delist = stock_data_row["delist_date"]
                    if delist is not None and not isinstance(delist, str) and pd.notna(delist):
                        return
                except Exception:
                    pass

        if isinstance(self.config.top_n_stocks, dict):
            target_n = self.config.top_n_stocks.get(regime, 1)
        else:
            target_n = self.config.top_n_stocks if self.config.top_n_stocks > 0 else 1
        target_ratio = self.config.base_position.get(regime, 0.5)
        single_cap = self.config.effective_single_cap(regime)

        # ATOS2 v1 + v2：凯利公式 + 自适应 Kelly 乘数（与 _execute_buy 同步）
        kelly_mult = getattr(self.config, "kelly_multiplier", 0.0)
        if kelly_mult > 0 and hasattr(self, "adaptive") and self.adaptive is not None:
            # ATOS2 v2：自适应 Kelly
            kelly_mult = self.adaptive.get_adaptive_kelly_multiplier()
            recent_trades = list(self.adaptive._recent_trades)
            if len(recent_trades) >= 10:
                wins = [t["pnl_pct"] for t in recent_trades if t["pnl_pct"] > 0]
                losses = [abs(t["pnl_pct"]) for t in recent_trades if t["pnl_pct"] <= 0]
                win_rate = len(wins) / len(recent_trades)
                avg_win = sum(wins) / len(wins) if wins else 0.02
                avg_loss = sum(losses) / len(losses) if losses else 0.02
                kelly_pct = max(0, win_rate - (1 - win_rate) * avg_loss / (avg_win + 1e-9)) * kelly_mult
                target_ratio = min(target_ratio, kelly_pct)

        target_value = self.cash * min(target_ratio, single_cap)

        shares = int(target_value / self._calc_buy_unit_cost(price) / 100) * 100
        if shares == 0:
            return

        cost = self._calc_buy_cost(shares, price)
        if cost > self.cash * 0.95:
            affordable = int(self.cash * 0.95 / self._calc_buy_unit_cost(price) / 100) * 100
            if affordable < 100:
                return
            shares = affordable
            cost = self._calc_buy_cost(shares, price)

        # 实际扣款
        self.cash -= cost

        # 创建 position（使用 execution_date 作为 entry_date）
        # 找对应的 trade_id（_execute_buy 写入的 date 与 execution_date 一致）
        matching_trade = None
        for t in reversed(self.trades):
            if t["action"] == "BUY" and t["symbol"] == symbol and t["date"] == execution_date:
                matching_trade = t
                break
        trade_id = matching_trade["trade_id"] if matching_trade else f"{symbol}_{execution_date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

        self.positions[symbol] = Position(
            symbol=symbol,
            entry_price=price,
            entry_date=execution_date,
            size=shares,
            entry_regime=regime,
            trade_id=trade_id,
        )

    def _calc_buy_unit_cost(self, price: float) -> float:
        """计算单股买入成本（含佣金最低5元）"""
        commission = max(price * self.config.commission_rate, 5.0 / 100)  # 最低 5 元
        transfer_fee = 0.00001  # 0.001% 沪市/万分之一深市
        return price * (1 + commission + transfer_fee)

    def _calc_buy_cost(self, shares: int, price: float) -> float:
        """计算买入总成本（含佣金最低5元 + 印花税仅卖出 + 过户费 + 滑点）"""
        gross = shares * price
        # 滑点：买入价格上浮 0.1% (模拟买入冲击)
        slippage_price = price * (1 + 0.001)
        gross_with_slippage = shares * slippage_price
        # 佣金：双边，最低 5 元
        commission = max(gross_with_slippage * self.config.commission_rate, 5.0)
        # 过户费：0.001%
        transfer_fee = gross_with_slippage * 0.00001
        return gross_with_slippage + commission + transfer_fee

    def _calc_sell_proceeds(self, shares: int, price: float) -> float:
        """计算卖出总所得（含佣金最低5元 + 印花税 + 过户费 + 滑点）"""
        # 滑点：卖出价格下浮 0.1% (模拟卖出冲击)
        slippage_price = price * (1 - 0.001)
        gross_with_slippage = shares * slippage_price
        # 佣金：双边，最低 5 元
        commission = max(gross_with_slippage * self.config.commission_rate, 5.0)
        # 印花税：仅卖出，0.1%
        stamp_tax = gross_with_slippage * self.config.stamp_tax_rate
        # 过户费：0.001%
        transfer_fee = gross_with_slippage * 0.00001
        return gross_with_slippage - commission - stamp_tax - transfer_fee

    def _execute_sell(self, date, symbol, price, ratio, reason):
        """执行卖出（支持分批 + 检查涨跌停/停牌 + 滑点）

        实际卖出统一由 _execute_sell_on_execution 在 T+1 开盘成交。
        本方法保留作为内部辅助（直接按给定 price 卖出，无 T+1 延迟）。
        """
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]

        # T+1 锁定期检查：买入当日不能卖
        if pos.entry_date == date:
            return  # 跳过当日卖出（同日 T+1 锁）

        target_shares = int(pos.size * ratio)
        sell_shares = (target_shares // 100) * 100
        sell_shares = min(sell_shares, pos.size)
        if sell_shares == 0:
            return

        proceeds = self._calc_sell_proceeds(sell_shares, price)
        self.cash += proceeds
        pos.size -= sell_shares

        buy_trade_id = getattr(pos, "trade_id", None)
        self.trades.append({
            "trade_id": buy_trade_id,
            "date": date, "action": "SELL", "symbol": symbol,
            "price": price, "shares": sell_shares, "reason": reason,
        })

        # spec §6.1：记录平仓到 adaptive tracker（用于滚动胜率）
        if hasattr(self, "adaptive") and self.adaptive is not None and pos.size == 0:
            try:
                pnl_pct = (price - pos.entry_price) / pos.entry_price
                self.adaptive.record_trade(pnl_pct, date)
            except Exception:
                pass

        if pos.size == 0:
            del self.positions[symbol]

    def _execute_sell_on_execution(self, symbol, execution_date, ratio, reason,
                                    market_df, stock_data):
        """T+1 开盘价成交（修复：符合 spec §4.1/§4.2 的"次日开盘"要求）

        涨跌停/停牌/退市检查：
        - 一字跌停 → 跳过，保留持仓（与买入 T+1 检查一致）
        - 停牌（volume=0）→ 跳过
        - 退市 → 跳过

        如果 T+1 跳过，下根 bar 再触发 pending_sell（这里简化：直接丢弃）
        """
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]

        # T+1 涨跌停/停牌/退市检查
        stock_data_row = self._get_stock_row(symbol, execution_date)
        if stock_data_row is not None:
            # 跌停：无法卖出
            if "is_limit_down" in stock_data_row.index:
                try:
                    if bool(stock_data_row["is_limit_down"]):
                        return  # 跌停日卖出被挡，保留持仓
                except Exception:
                    pass
            # 停牌：无法卖出
            if "volume" in stock_data_row.index:
                try:
                    if float(stock_data_row["volume"]) == 0:
                        return
                except Exception:
                    pass

        # 获取 T+1 开盘价
        try:
            if symbol == self.config.symbol or symbol not in stock_data:
                execution_price = float(market_df.loc[execution_date, "open"])
            else:
                execution_price = float(stock_data[symbol].loc[execution_date, "open"])
        except Exception:
            # 找不到 T+1 开盘价，丢弃
            return

        # 实际卖出
        self._execute_sell(execution_date, symbol, execution_price, ratio, reason)

    def _record_equity(self, date, market_df, stock_data, regime):
        """记录每日净值（修复：使用 _gather_position_prices 一致的查价逻辑）"""
        prices = self._gather_position_prices(date, market_df, stock_data)
        position_value = 0.0
        for symbol, pos in self.positions.items():
            # 持仓只在 entry_date 及之后计入净值
            if pos.entry_date > date:
                continue
            if symbol in prices:
                px = prices[symbol]
            else:
                px = pos.entry_price
            position_value += pos.size * px
        equity = self.cash + position_value

        # 更新回撤跟踪
        if self.drawdown_tracker is not None:
            self.drawdown_tracker.update(equity, date)

        # ATOS2 v1：回撤阶梯检测
        self._check_drawdown_step(equity, date)

        self.equity_history.append({
            "date": date,
            "equity": equity,
            "cash": self.cash,
            "position_value": position_value,
            "state": regime,
            "n_positions": len(self.positions),
            "drawdown_step": self._drawdown_step_active,
        })

    def _check_drawdown_step(self, equity: float, date: pd.Timestamp):
        """ATOS2 v1 回撤阶梯检测

        | 净值回撤 | 仓位调整 | 持续时间 |
        |---------|---------|---------|
        | 5% | 仓位 × 0.7 | 5 个交易日 |
        | 10% | 仓位 × 0.4 | 10 个交易日 |
        | 15% | 空仓 | 5 个交易日 |
        """
        if self.drawdown_tracker is None or not self.equity_history:
            return

        # 阶梯到期后重置
        if self._drawdown_step_until is not None and date >= self._drawdown_step_until:
            self._drawdown_step_active = 0
            self._drawdown_step_until = None

        # 当前回撤
        current_dd = getattr(self.drawdown_tracker, "current_dd", 0.0)
        if current_dd is None:
            return

        # 检查触发新阶梯（按降级触发，单向升级）
        steps = [
            (-0.05, 1, 5),    # 5% 回撤 → 阶梯 1，持续 5 日
            (-0.10, 2, 10),   # 10% 回撤 → 阶梯 2，持续 10 日
            (-0.15, 3, 5),    # 15% 回撤 → 阶梯 3（空仓），持续 5 日
        ]
        for threshold, level, days in steps:
            if current_dd <= threshold and self._drawdown_step_active < level:
                self._drawdown_step_active = level
                self._drawdown_step_until = date + pd.tseries.offsets.BDay(days)
                break

    def _get_position_cap_with_step(self, regime_cap: float) -> float:
        """ATOS2 v1：应用回撤阶梯调整后的仓位上限"""
        step_multiplier = {
            0: 1.0,
            1: 0.7,   # 5% 回撤
            2: 0.4,   # 10% 回撤
            3: 0.0,   # 15% 回撤 → 空仓
        }.get(self._drawdown_step_active, 1.0)
        return regime_cap * step_multiplier

    def _build_result(self, regime_df: pd.DataFrame) -> "BacktestResult":
        equity_df = pd.DataFrame(self.equity_history)
        if equity_df.empty:
            empty = pd.Series(dtype=float)
            return BacktestResult(
                equity_curve=empty, trades=pd.DataFrame(),
                daily_returns=empty, metrics={},
            )
        equity_df = equity_df.set_index("date")
        equity_curve = equity_df["equity"]
        daily_returns = equity_curve.pct_change().dropna()
        trades_df = pd.DataFrame(self.trades)

        from .metrics import compute_all_metrics
        metrics = compute_all_metrics(equity_curve, trades_df)

        regime_h = pd.DataFrame(self.regime_history)
        if not regime_h.empty:
            regime_h = regime_h.set_index("date")

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades_df,
            daily_returns=daily_returns,
            metrics=metrics,
            regime_history=regime_h,
        )

    def run_single_stock(self, df: pd.DataFrame) -> "BacktestResult":
        """单标的回测（向后兼容）"""
        return self.run(market_df=df, stock_data={self.config.symbol: df})
