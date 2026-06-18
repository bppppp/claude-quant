# 08 - 回测引擎

## 8.1 职责

提供**完整的回测能力**：
- 多标的组合回测（BacktestEngine 持有 dict[symbol, Position]）
- 单标的回测（向后兼容）
- 完整绩效指标计算
- Walk-Forward Analysis
- 参数扰动测试

## 8.2 模块结构

```
backtest/
├── __init__.py
├── engine.py           # BacktestEngine（多标的组合）
├── metrics.py          # 绩效指标
├── walk_forward.py     # Walk-Forward
├── perturbation.py     # 参数扰动
└── report.py           # 报告生成
```

## 8.3 回测引擎（**多标的组合版**，修复 A1）

```python
# backtest/engine.py
import pandas as pd
import numpy as np
import uuid
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class BacktestResult:
    """回测结果"""
    equity_curve: pd.Series
    trades: pd.DataFrame
    daily_returns: pd.Series
    metrics: dict


class BacktestEngine:
    """回测引擎（**多标的组合版**）

    修复 A1:
    - 旧版用 self.position（单一持仓），与"组合"策略矛盾
    - 新版用 self.positions: dict[symbol, Position]
    - 按 trade_id 配对，支持分批
    """

    def __init__(self, config):
        self.config = config
        self.positions: dict[str, object] = {}  # {symbol: Position}
        self.cash = config.initial_capital
        self.trades = []  # 所有成交（含分批）
        self.equity_history = []

    def run(
        self,
        market_df: pd.DataFrame,      # 大盘数据（用于状态识别）
        stock_data: dict[str, pd.DataFrame] = None,  # 个股数据 {symbol: df}
        benchmark_df: pd.DataFrame = None,  # 基准
        test_only_period: tuple = None  # 修复 B7-02: (start, end)
    ) -> "BacktestResult":
        """运行组合回测

        Args:
            market_df: 大盘指数数据（含所有指标）
            stock_data: 个股数据字典（None 则单标的回测模式）
            benchmark_df: 基准数据（用于计算 alpha/beta）
            test_only_period: 修复 B7-02，只回测 (start, end) 区间

        Returns:
            BacktestResult
        """
        # 1. 大盘状态识别
        from regime import detect_full_regime
        regime_df = detect_full_regime(market_df, self.config)

        # 修复 B7-02: 处理 test_only_period 限制
        start_idx = 0
        end_idx = len(market_df)
        if test_only_period is not None:
            period_start, period_end = test_only_period
            try:
                start_idx = market_df.index.get_loc(pd.Timestamp(period_start))
            except KeyError:
                start_idx = 0
            try:
                end_idx = market_df.index.get_loc(pd.Timestamp(period_end)) + 1
            except KeyError:
                end_idx = len(market_df)

        # 2. 逐日循环
        for i in range(start_idx, end_idx):
            if i < 1:
                continue
            date = market_df.index[i]
            # 修复 [v8.5] D7: 用 effective_state 做状态判断，target_position 做仓位限制
            # effective_state 已包含 choppy_bear_active 的影响
            regime = regime_df.loc[date, "effective_state"]
            target_position_cap = regime_df.loc[date, "target_position"]
            current_prices = self._get_current_prices(date, market_df, stock_data)

            # 处理卖出
            self._process_sells(date, current_prices, regime)

            # 处理买入（如果还有空位）
            self._process_buys(date, current_prices, regime, market_df, stock_data)

            # 记录净值
            self._record_equity(date, current_prices, regime)

        # 3. 收尾
        return self._build_result()

    def _get_current_prices(
        self, date, market_df, stock_data
    ) -> dict[str, float]:
        """获取所有持仓 + 候选股的当前价"""
        prices = {}
        # 已持仓的股票
        for symbol in self.positions:
            if stock_data and symbol in stock_data:
                if date in stock_data[symbol].index:
                    prices[symbol] = stock_data[symbol].loc[date, "close"]
            elif date in market_df.index and symbol == self.config.symbol:
                prices[symbol] = market_df.loc[date, "close"]
        return prices

    def _process_sells(self, date, current_prices, regime):
        """处理所有持仓的卖出检查"""
        from risk.stop_loss import check_exit

        for symbol in list(self.positions.keys()):
            if symbol not in current_prices:
                continue
            pos = self.positions[symbol]
            current_price = current_prices[symbol]
            # 获取当前 ATR
            current_atr = self._get_atr(symbol, date)
            if current_atr <= 0:
                current_atr = current_price * 0.02

            should_sell, ratio, reason = check_exit(
                pos, current_price, current_atr, date, regime, self.config
            )

            if should_sell:
                self._execute_sell(date, symbol, current_price, ratio, reason)

    def _process_buys(self, date, current_prices, regime, market_df, stock_data):
        """处理买入（多标的选股）"""
        from selection.selector import StockSelector
        # 注：信号生成由 selector.select() 内部调用 generate_buy_signals(df, regime, config)

        # 修复 #8: CRASH 状态不处理买入（避免在崩盘中买入）
        if regime == "CRASH":
            return

        # 修复 B18: 用 top_n_stocks（持仓只数），不是 max_holding_days（天数）
        if isinstance(self.config.top_n_stocks, dict):
            target_n = self.config.top_n_stocks.get(regime, 10)
        else:
            target_n = self.config.top_n_stocks

        if len(self.positions) >= target_n:
            return  # 已满仓

        # 2. 选股（单标的时跳过）
        candidates = []
        if stock_data:
            # 多标的：用选股器
            selector = StockSelector(self.config)
            candidates = selector.select(
                date=date, stock_data=stock_data,
                state=regime, top_n=target_n * 2
            )
        else:
            # 单标的模式
            if "sig_final" in market_df.columns:
                if market_df.loc[date, "sig_final"] == 1:
                    candidates = [self.config.symbol]

        # 3. 对每只候选股判断是否买入
        n_to_buy = target_n - len(self.positions)
        for symbol in candidates[:n_to_buy]:
            if symbol in self.positions:
                continue
            if symbol not in current_prices and stock_data:
                continue

            # 检查冷却期
            from risk.cooldown import CooldownManager
            if not hasattr(self, "_cooldown"):
                self._cooldown = CooldownManager()
            can_buy, _ = self._cooldown.can_buy(symbol, date, regime)
            if not can_buy:
                continue

            # 修复 D8 + [v8.3]: T+1 开盘价成交（避免未来函数）
            # 关键修复：成交日应为 next_day，而非 date。
            # 否则 position.entry_date=date 会导致 holding_days 比实际多 1，
            # 并在回测中错误地触发时间止损。
            current_date_ts = pd.Timestamp(date)
            next_day = current_date_ts + pd.tseries.offsets.BDay(1)
            try:
                next_open_price = market_df.loc[next_day, "open"]
            except KeyError:
                next_open_price = current_prices.get(symbol, market_df.loc[date, "close"])
                # 数据无 next_day 时直接用今日 close（无法避免未来函数，记录警告）
                import warnings
                warnings.warn(
                    f"{symbol} 在 {next_day} 无 open 数据，回退到 {date} 的 close，"
                    f"存在未来函数风险"
                )
                next_day = current_date_ts  # 兜底
            self._execute_buy(next_day, symbol, next_open_price, regime)

    def _execute_buy(self, date, symbol, price, regime):
        """执行买入（单只）"""
        from risk.position import Position

        # 1. 计算目标仓位（修复 [v8.5] H2: 使用 effective_single_cap）
        if isinstance(self.config.top_n_stocks, dict):
            target_n = self.config.top_n_stocks.get(regime, 10)
        else:
            target_n = self.config.top_n_stocks
        target_ratio = self.config.base_position.get(regime, 0.5)
        # 修复 H2: 用 effective_single_cap 取代硬编码 15%
        single_cap = self.config.effective_single_cap(regime)
        target_value = self.cash * min(target_ratio, single_cap)
        shares = int(target_value / price / 100) * 100
        if shares == 0:
            return

        # 2. 修复 C2 + C3: 交易费率（佣金 0.025%）+ 5% 现金缓冲
        commission_rate = 0.00025
        cost = shares * price * (1 + commission_rate)
        if cost > self.cash * 0.95:
            affordable_shares = int(self.cash * 0.95 / price / (1 + commission_rate) / 100) * 100
            if affordable_shares < 100:
                return
            shares = affordable_shares
            cost = shares * price * (1 + commission_rate)

        self.cash -= cost
        # 修复 B5 + C42: trade_id 唯一标识，用 uuid 防同日冲突
        trade_id = f"{symbol}_{date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        self.positions[symbol] = Position(
            symbol=symbol, entry_price=price, entry_date=date,
            size=shares, entry_regime=regime,
            trade_id=trade_id  # 修复 #5: 同步赋值给 pos
        )
        self.trades.append({
            "trade_id": trade_id,
            "date": date, "action": "BUY", "symbol": symbol,
            "price": price, "shares": shares, "regime": regime
        })

    def _execute_sell(self, date, symbol, price, ratio, reason):
        """执行卖出（支持分批，修复 [v8.4] A31）

        修复说明：
        - 旧版 sell_shares = int(pos.size * ratio / 100) * 100 错误：
          ratio 是 0-1 范围（如 0.5 = 卖一半），除以 100 后通常 < 1，
          int(...) 永远为 0，导致 sell_shares = 0。
        - 修复后：先算目标股数（ratio * size），再向下取整到 100 的倍数。
        """
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]

        # 修复 [v8.4] A31: ratio 是 0-1，int(pos.size * ratio) // 100 * 100
        target_shares = int(pos.size * ratio)
        sell_shares = (target_shares // 100) * 100
        sell_shares = min(sell_shares, pos.size)
        if sell_shares == 0:
            return

        # 修复 C2: 印花税 0.1% + 佣金 0.025%
        commission_rate = 0.00025
        stamp_tax_rate = 0.001
        proceeds = sell_shares * price * (1 - commission_rate - stamp_tax_rate)
        self.cash += proceeds
        pos.size -= sell_shares

        # 修复 C4: 用 pos.trade_id 关联原始买入
        buy_trade_id = getattr(pos, "trade_id", None)
        self.trades.append({
            "trade_id": buy_trade_id,
            "date": date, "action": "SELL", "symbol": symbol,
            "price": price, "shares": sell_shares, "reason": reason
        })

        if pos.size == 0:
            del self.positions[symbol]

    def _record_equity(self, date, current_prices, regime):
        """记录每日净值"""
        position_value = sum(
            pos.size * current_prices.get(symbol, pos.entry_price)
            for symbol, pos in self.positions.items()
        )
        equity = self.cash + position_value
        self.equity_history.append({
            "date": date,
            "equity": equity,
            "cash": self.cash,
            "position_value": position_value,
            "state": regime,
            "n_positions": len(self.positions)
        })

    def _get_atr(self, symbol, date) -> float:
        """获取指定日期的 ATR"""
        return 0.0  # 由 check_exit 内部 fallback

    def _build_result(self) -> "BacktestResult":
        """构建回测结果"""
        equity_df = pd.DataFrame(self.equity_history).set_index("date")
        equity_curve = equity_df["equity"]
        daily_returns = equity_curve.pct_change().dropna()
        trades_df = pd.DataFrame(self.trades)

        from backtest.metrics import compute_all_metrics
        metrics = compute_all_metrics(equity_curve, trades_df)

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades_df,
            daily_returns=daily_returns,
            metrics=metrics
        )

    def run_single_stock(self, df: pd.DataFrame) -> "BacktestResult":
        """单标的回测（向后兼容）"""
        return self.run(
            market_df=df,
            stock_data={self.config.symbol: df}
        )
```

## 8.4 绩效指标

```python
# backtest/metrics.py
import pandas as pd
import numpy as np


def compute_all_metrics(equity_curve: pd.Series,
                          trades: pd.DataFrame = None) -> dict:
    """计算完整绩效指标

    Returns:
        dict of metrics
    """
    metrics = {}

    # 基础收益（修复 C32: 加空数据保护）
    n_days = len(equity_curve)
    if n_days < 2:
        return {
            "total_return": 0, "annual_return": 0, "n_years": 0,
            "volatility": 0, "max_drawdown": 0, "sharpe": 0
        }
    n_years = n_days / 252
    first_eq = equity_curve.iloc[0]
    if first_eq == 0 or pd.isna(first_eq):
        total_return = 0
    else:
        total_return = equity_curve.iloc[-1] / first_eq - 1
    annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    metrics["total_return"] = total_return
    metrics["annual_return"] = annual_return
    metrics["n_years"] = n_years

    # 风险
    daily_ret = equity_curve.pct_change().dropna()
    metrics["volatility"] = daily_ret.std() * np.sqrt(252)
    metrics["downside_vol"] = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    metrics["max_drawdown"] = (equity_curve / equity_curve.cummax() - 1).min()
    metrics["drawdown_duration"] = compute_max_drawdown_duration(equity_curve)

    # VaR / CVaR
    metrics["var_95"] = -daily_ret.quantile(0.05)
    metrics["cvar_95"] = -daily_ret[daily_ret <= daily_ret.quantile(0.05)].mean()

    # 风险调整
    rf = 0.025
    excess = annual_return - rf
    metrics["sharpe"] = excess / metrics["volatility"] if metrics["volatility"] > 0 else 0
    metrics["sortino"] = excess / metrics["downside_vol"] if metrics["downside_vol"] > 0 else 0
    metrics["calmar"] = annual_return / abs(metrics["max_drawdown"]) if metrics["max_drawdown"] < 0 else 0
    metrics["omega"] = compute_omega(daily_ret, threshold=0)

    # 月度 / 季度胜率（修复 C28: 用 ME/QE 而非 M/Q）
    monthly = equity_curve.resample("ME").last().pct_change().dropna()
    quarterly = equity_curve.resample("QE").last().pct_change().dropna()
    metrics["monthly_win_rate"] = (monthly > 0).mean()
    metrics["quarterly_win_rate"] = (quarterly > 0).mean()

    # 交易统计
    if trades is not None and not trades.empty:
        metrics.update(compute_trade_metrics(trades))

    # 稳定性
    monthly_ret = equity_curve.resample("ME").last().pct_change().dropna()
    metrics["monthly_vol"] = monthly_ret.std()
    metrics["rolling_12m_sharpe"] = compute_rolling_sharpe(daily_ret, window=252)

    return metrics


def compute_max_drawdown_duration(equity: pd.Series) -> int:
    """最大回撤持续时间（天）"""
    cummax = equity.cummax()
    is_drawdown = equity < cummax
    if not is_drawdown.any():
        return 0
    groups = (is_drawdown != is_drawdown.shift()).cumsum()
    return int(is_drawdown.groupby(groups).sum().max())


def compute_omega(returns: pd.Series, threshold: float = 0) -> float:
    """Omega 比率（修复 C26: 用 999 替 inf）"""
    excess = returns - threshold
    gain = excess[excess > 0].sum()
    loss = -excess[excess < 0].sum()
    if loss == 0:
        return 999.0
    return gain / loss


def compute_rolling_sharpe(returns: pd.Series, window: int = 252) -> pd.Series:
    """滚动年化夏普"""
    rolling_mean = returns.rolling(window).mean() * 252
    rolling_std = returns.rolling(window).std() * np.sqrt(252)
    return rolling_mean / rolling_std


def compute_trade_metrics(trades: pd.DataFrame) -> dict:
    """交易相关指标（修复 C19: 按 trade_id 配对，支持分批）"""
    metrics = {
        "n_buys": len(trades[trades["action"] == "BUY"]),
        "n_sells": len(trades[trades["action"] == "SELL"])
    }
    metrics["n_trades"] = min(metrics["n_buys"], metrics["n_sells"])

    if trades.empty or "trade_id" not in trades.columns:
        return _compute_trade_metrics_legacy(trades)

    # 按 trade_id 配对
    paired_list = []
    for trade_id, group in trades.groupby("trade_id"):
        buys = group[group["action"] == "BUY"]
        sells = group[group["action"] == "SELL"]
        if not buys.empty and not sells.empty:
            entry_price = (buys["price"] * buys["shares"]).sum() / buys["shares"].sum()
            exit_price = (sells["price"] * sells["shares"]).sum() / sells["shares"].sum()
            paired_list.append({
                "trade_id": trade_id,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "shares": min(buys["shares"].sum(), sells["shares"].sum()),
                "pnl": (exit_price - entry_price) / entry_price
            })

    if not paired_list:
        return metrics

    paired = pd.DataFrame(paired_list)
    win = paired[paired["pnl"] > 0]
    loss = paired[paired["pnl"] <= 0]
    metrics["win_rate"] = len(win) / len(paired) if len(paired) > 0 else 0
    metrics["avg_pnl"] = paired["pnl"].mean()
    metrics["avg_win"] = win["pnl"].mean() if not win.empty else 0
    metrics["avg_loss"] = loss["pnl"].mean() if not loss.empty else 0
    metrics["profit_loss_ratio"] = (
        abs(metrics["avg_win"] / metrics["avg_loss"])
        if metrics["avg_loss"] != 0 else np.inf
    )
    metrics["max_consecutive_wins"] = compute_max_consecutive(paired["pnl"] > 0)
    metrics["max_consecutive_losses"] = compute_max_consecutive(paired["pnl"] <= 0)
    metrics["max_pnl"] = paired["pnl"].max()
    metrics["min_pnl"] = paired["pnl"].min()

    return metrics


def _compute_trade_metrics_legacy(trades: pd.DataFrame) -> dict:
    """旧版交易指标计算（无 trade_id 时用，仅向后兼容）"""
    buy_trades = trades[trades["action"] == "BUY"]
    sell_trades = trades[trades["action"] == "SELL"]
    metrics = {"n_buys": len(buy_trades), "n_sells": len(sell_trades)}
    if buy_trades.empty or sell_trades.empty:
        return metrics
    n = min(len(buy_trades), len(sell_trades))
    paired = pd.DataFrame({
        "entry_price": buy_trades["price"].iloc[:n].values,
        "exit_price": sell_trades["price"].iloc[:n].values
    })
    paired["pnl"] = (paired["exit_price"] - paired["entry_price"]) / paired["entry_price"]
    win = paired[paired["pnl"] > 0]
    loss = paired[paired["pnl"] <= 0]
    metrics["n_trades"] = n
    metrics["win_rate"] = len(win) / n
    metrics["avg_pnl"] = paired["pnl"].mean()
    metrics["avg_win"] = win["pnl"].mean() if not win.empty else 0
    metrics["avg_loss"] = loss["pnl"].mean() if not loss.empty else 0
    metrics["profit_loss_ratio"] = (
        abs(metrics["avg_win"] / metrics["avg_loss"])
        if metrics["avg_loss"] != 0 else np.inf
    )
    return metrics


def compute_max_consecutive(series: pd.Series) -> int:
    """最大连续 True 数量"""
    if series.empty:
        return 0
    groups = (series != series.shift()).cumsum()
    return series.groupby(groups).sum().max()
```

## 8.5 Walk-Forward Analysis

```python
# backtest/walk_forward.py
import pandas as pd
import numpy as np


def walk_forward(
    df: pd.DataFrame,
    config,
    train_years: int = 3,
    test_years: int = 1,
    step_years: int = 1
) -> dict:
    """Walk-Forward Analysis"""
    start_year = df.index.year.min()
    end_date = df.index.max()  # 修复 C18: 真实结束日期
    end_year = end_date.year

    folds = []
    fold_start = start_year

    # 修复 C18 + C19: 用真实日期判断
    while True:
        test_end_date_candidate = pd.Timestamp(f"{fold_start + train_years + test_years}-12-31")
        if test_end_date_candidate > end_date:
            break
        train_start = f"{fold_start}-01-01"
        train_end = f"{fold_start + train_years}-12-31"
        test_start = f"{fold_start + train_years}-01-01"
        test_end = min(
            test_end_date_candidate,
            end_date
        ).strftime("%Y-%m-%d")

        # 修复 B9: 传完整上下文（含 warmup）
        full_context = df[train_start:test_end]
        engine = BacktestEngine(config)
        result = engine.run(full_context, test_only_period=(test_start, test_end))

        folds.append({
            "fold": len(folds) + 1,
            "train_period": (train_start, train_end),
            "test_period": (test_start, test_end),
            "annual_return": result.metrics["annual_return"],
            "sharpe": result.metrics["sharpe"],
            "max_drawdown": result.metrics["max_drawdown"]
        })

        fold_start += step_years

    if not folds:
        raise ValueError("Not enough data for walk-forward analysis")

    return {
        "folds": pd.DataFrame(folds),
        "summary": {
            "mean_annual_return": np.mean([f["annual_return"] for f in folds]),
            "mean_sharpe": np.mean([f["sharpe"] for f in folds]),
            "mean_max_dd": np.mean([f["max_drawdown"] for f in folds])
        }
    }
```

## 8.6 参数扰动测试

```python
# backtest/perturbation.py
import pandas as pd
import numpy as np
from copy import deepcopy


def _get_nested_value(obj, dotted_key: str):
    """修复 B3: 通过点号路径获取嵌套属性（如 base_position.BULL）"""
    parts = dotted_key.split(".")
    value = obj
    for part in parts:
        value = getattr(value, part) if not isinstance(value, dict) else value[part]
    return value


def _set_nested_value(obj, dotted_key: str, value):
    """修复 B3: 通过点号路径设置嵌套属性"""
    parts = dotted_key.split(".")
    target = obj
    for part in parts[:-1]:
        target = getattr(target, part) if not isinstance(target, dict) else target[part]
    final_key = parts[-1]
    if isinstance(target, dict):
        target[final_key] = value
    else:
        setattr(target, final_key, value)


def parameter_perturbation(
    base_config,
    df: pd.DataFrame,
    params_to_test: list[str] = None,
    perturbation: float = 0.2,
    n_trials: int = 30,
    random_seed: int = 42  # 修复 [v8.4] A36: 默认 seed 保证可复现
) -> pd.DataFrame:
    """参数扰动测试（修复 B3 + C20 + [v8.4] A36/A37: 支持嵌套键、可复现、除零保护）"""
    from backtest.engine import BacktestEngine

    # 修复 [v8.4] A36: 设置 seed
    np.random.seed(random_seed)

    base_dict = base_config.to_dict() if hasattr(base_config, "to_dict") else vars(base_config)

    # 修复 C20: 递归展开 dict 内的数值参数
    if params_to_test is None:
        params_to_test = []
        for k, v in base_dict.items():
            if isinstance(v, (int, float)):
                params_to_test.append(k)
            elif isinstance(v, dict):
                for sub_k in v:
                    if isinstance(v[sub_k], (int, float)):
                        params_to_test.append(f"{k}.{sub_k}")

    results = []

    for param_name in params_to_test:
        base_value = _get_nested_value(base_config, param_name)
        for trial in range(n_trials):
            perturbed = base_value * (1 + np.random.uniform(-perturbation, perturbation))

            test_config = deepcopy(base_config)
            _set_nested_value(test_config, param_name, perturbed)

            engine = BacktestEngine(test_config)
            result = engine.run(df)

            # 修复 [v8.4] A37: base_value=0 时 ratio=0 而非除零异常
            ratio = (perturbed / base_value - 1) if base_value != 0 else 0

            results.append({
                "param": param_name,
                "trial": trial,
                "base_value": base_value,
                "perturbed_value": perturbed,
                "ratio": ratio,
                **result.metrics
            })

    return pd.DataFrame(results)


def identify_fragile_params(
    perturb_results: pd.DataFrame,
    metric: str = "max_drawdown",
    threshold: float = 0.30
) -> pd.DataFrame:
    """识别脆弱参数"""
    summary = perturb_results.groupby("param")[metric].agg(
        ["mean", "std", "min", "max"]
    )
    summary["cv"] = summary["std"] / summary["mean"].abs()
    summary["fragility"] = (summary["max"] - summary["min"]) / summary["mean"].abs()
    return summary[summary["fragility"] > threshold].sort_values(
        "fragility", ascending=False
    )
```

## 8.7 报告生成

```python
# backtest/report.py
import pandas as pd
import os


def generate_report(result, output_dir: str = "reports/"):
    """生成回测报告"""
    os.makedirs(output_dir, exist_ok=True)

    # 1. 文本报告
    report_path = f"{output_dir}/backtest_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("ATOS 策略回测报告\n")
        f.write("=" * 60 + "\n\n")
        f.write("【收益指标】\n")
        f.write(f"  年化收益: {result.metrics['annual_return']:.2%}\n")
        f.write(f"  累计收益: {result.metrics['total_return']:.2%}\n\n")
        f.write("【风险指标】\n")
        f.write(f"  最大回撤: {result.metrics['max_drawdown']:.2%}\n")
        f.write(f"  年化波动率: {result.metrics['volatility']:.2%}\n")
        f.write(f"  VaR(95%): {result.metrics['var_95']:.2%}\n")
        f.write(f"  CVaR(95%): {result.metrics['cvar_95']:.2%}\n\n")
        f.write("【风险调整收益】\n")
        f.write(f"  Sharpe: {result.metrics['sharpe']:.2f}\n")
        f.write(f"  Sortino: {result.metrics['sortino']:.2f}\n")
        f.write(f"  Calmar: {result.metrics['calmar']:.2f}\n")
        omega = result.metrics['omega']
        f.write(f"  Omega: {999.0 if omega >= 999 else omega:.2f}\n\n")
        f.write("【交易统计】\n")
        f.write(f"  交易次数: {result.metrics.get('n_trades', 0)}\n")
        f.write(f"  胜率: {result.metrics.get('win_rate', 0):.2%}\n")
        f.write(f"  盈亏比: {result.metrics.get('profit_loss_ratio', 0):.2f}\n")
        f.write(f"  最大连盈: {result.metrics.get('max_consecutive_wins', 0)}\n")
        f.write(f"  最大连亏: {result.metrics.get('max_consecutive_losses', 0)}\n")

    # 2. CSV 输出
    result.equity_curve.to_csv(f"{output_dir}/equity_curve.csv")
    result.trades.to_csv(f"{output_dir}/trades.csv", index=False)

    # 3. 可视化
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(12, 8))
        axes[0].plot(result.equity_curve.index, result.equity_curve.values)
        axes[0].set_title("Equity Curve")
        axes[0].grid(True)

        cummax = result.equity_curve.cummax()
        dd = (result.equity_curve - cummax) / cummax
        axes[1].fill_between(dd.index, dd.values, 0, alpha=0.3, color="red")
        axes[1].set_title("Drawdown")
        axes[1].grid(True)

        plt.tight_layout()
        plt.savefig(f"{output_dir}/equity_curve.png", dpi=100)
        plt.close()
    except ImportError:
        pass

    return report_path
```

## 8.8 性能基准

| 操作 | 不预计算 | 预计算 | 提升 |
|---|---|---|---|
| 单标的回测 | 30s | 5min | 6x |
| Walk-Forward（5 轮） | 2.5h | 30min | 5x |
| 参数扰动（30 试 × N 参数） | 1h | 10min | 6x |

## 8.9 关键年份分析

```python
def analyze_key_years(equity_curve: pd.Series) -> dict:
    """分析关键年份表现（修复 C27: 数据缺失时返回 N/A 不报错）"""
    key_years = {
        2018: "贸易战", 2019: "牛启动", 2020: "疫情",
        2021: "牛尾", 2022: "杀跌", 2023: "震荡",
        2024: "阴跌", 2025: "反弹"
    }

    results = {}
    for year, name in key_years.items():
        year_data = equity_curve[equity_curve.index.year == year]
        if year_data.empty:
            results[year] = {"name": name, "data": "N/A"}
            continue
        start = year_data.iloc[0]
        end = year_data.iloc[-1]
        if start == 0:
            results[year] = {"name": name, "data": "N/A"}
            continue
        ret = (end / start) - 1
        max_dd = (year_data / year_data.cummax() - 1).min()
        results[year] = {"name": name, "return": ret, "max_drawdown": max_dd}
    return results
```

## 8.10 单元测试

```python
# tests/test_backtest.py
import pytest
import pandas as pd
import numpy as np


def test_backtest_basic():
    """基本回测流程"""
    np.random.seed(42)
    n = 252
    close = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range("2024-01-01", periods=n)
    )
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1e6, 1e7, n)
    })

    from backtest.engine import BacktestEngine
    from config.strategy_config import StrategyConfig
    config = StrategyConfig()
    config.initial_capital = 1_000_000
    engine = BacktestEngine(config)
    result = engine.run(df)

    assert result.equity_curve is not None
    assert "annual_return" in result.metrics


def test_metrics_calculation():
    """指标计算正确性"""
    np.random.seed(42)
    equity = pd.Series(np.cumsum(np.random.randn(252)) + 100)
    from backtest.metrics import compute_all_metrics
    metrics = compute_all_metrics(equity)
    assert "sharpe" in metrics
    assert "max_drawdown" in metrics
```

## 8.11 完整回测流程示例（v8.1 含大盘数据）

```python
# scripts/run_backtest_with_benchmark.py
"""完整回测示例：含大盘数据加载、状态识别、组合回测"""
import sys
sys.path.insert(0, ".")
from pathlib import Path
import pandas as pd

from data.benchmark_loader import load_benchmark
from data.loader import load_stock_series
from indicators.pipeline import calc_indicators_with_cache
from regime import detect_full_regime
from backtest.engine import BacktestEngine
from config import load_config
from backtest.metrics import compute_all_metrics
from backtest.report import generate_report


def run_full_backtest():
    """完整回测（沪深 300 ETF vs 沪深 300 指数基准）"""
    # 1. 加载配置
    config = load_config("config/params.yaml")

    # 2. 加载大盘数据（沪深 300 指数，**v8.1 新增**）
    print("[1/5] 加载大盘数据（沪深 300）...")
    market_df = load_benchmark("hs300", start="2016-01-01", end="2025-12-31")
    market_df = calc_indicators_with_cache("hs300", df=market_df, force_recalc=False)
    print(f"  {len(market_df)} 行 × {len(market_df.columns)} 列")

    # 3. 加载候选股票
    print("[2/5] 加载候选股票...")
    stock_data = {}
    candidate_symbols = ["000001", "000002", "000063", "600519", "000858"]
    for symbol in candidate_symbols:
        try:
            df = load_stock_series(symbol, start="2016-01-01", end="2025-12-31")
            df = calc_indicators_with_cache(symbol, df=df, force_recalc=False)
            stock_data[symbol] = df
        except FileNotFoundError:
            print(f"  跳过 {symbol}: 数据不存在")

    # 4. 加载基准
    print("[3/5] 加载基准...")
    benchmark_df = market_df.copy()

    # 5. 状态识别
    print("[4/5] 大盘状态识别...")
    regime_df = detect_full_regime(market_df, config)
    print(f"  状态分布: {regime_df['state'].value_counts().to_dict()}")

    # 6. 组合回测
    print("[5/5] 运行组合回测...")
    engine = BacktestEngine(config)
    result = engine.run(
        market_df=market_df,
        stock_data=stock_data,
        benchmark_df=benchmark_df
    )

    # 7. 报告
    print("\n=== 回测结果 ===")
    for k, v in result.metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.2%}")
        else:
            print(f"  {k}: {v}")

    # 8. 生成报告
    generate_report(result)

    return result


if __name__ == "__main__":
    result = run_full_backtest()
```

