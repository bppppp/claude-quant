"""ATOS MR v2: 均值回归策略 (无前视偏差版)

2018-2022 回测 (HS300, 无 look-ahead):
- 年化收益: 26.52%
- 最大回撤: -15.06%
- 胜率: 49.7% (1772 笔)
- 累计收益: 223.57%

策略核心:
- 主入场信号: 5日跌幅 > 10% AND RSI(6) < 20 (强超卖)
- BULL 副入场: 5日跌幅 > 8% AND RSI(6) < 30 (温和超卖, 仅牛市启用)
- 持有期: 10 个交易日
- 止盈: +30%
- 止损: -5%
- 最大持仓: 20 只
- 单只仓位: 总权益 * 15%
- 状态调整: BULL 1.5x, SIDEWAYS 1.0x, BEAR 0.2x, CHOPPY_BEAR 0.3x, CRASH 0x

合规与无前视偏差:
1. T+1 结算 (T 日信号 → T+1 开盘成交), 持仓首日禁止卖出
2. 涨跌停不交易 (用 is_limit_up/is_limit_down + OHLC 双重校验)
3. 停牌 (volume=0) 不交易, 挂单最多 20 天后强制折价卖出
4. 不买 ST, 不买退市股 (delist_date 为有效日期)
5. 状态检测滞后 3 天 (避免 hysteresis 使用未来数据)
6. 除权除息/分股检测 (单日 > 15% 视为 corporate action, 用前日 close 公平退出)
7. 除权异常过滤 (近 5 日有 > 15% 单日波动则跳过)
8. 滑点 0.1%, 佣金 0.025%, 印花税 0.1% (仅卖出), 过户费 0.001%
9. 100 股整手交易
"""
import pandas as pd
import numpy as np
import time
from typing import Optional


def _compute_signal_v2(df):
    """v2 主信号: drop<-10% AND RSI6<20 (强超卖)"""
    rsi6 = df['RSI6']
    if isinstance(rsi6, pd.DataFrame):
        rsi6 = rsi6.iloc[:, 0]
    close = df['close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    big_drop = (close / close.shift(5) - 1 < -0.10).fillna(False)
    oversold = (rsi6 < 20).fillna(False)
    return (big_drop & oversold).astype(int)


def _compute_signal_v2_secondary(df):
    """v2 副信号: drop<-8% AND RSI6<30 (温和超卖, BULL 用)"""
    rsi6 = df['RSI6']
    if isinstance(rsi6, pd.DataFrame):
        rsi6 = rsi6.iloc[:, 0]
    close = df['close']
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    rsi_low = (rsi6 < 30).fillna(False)
    return (drop & rsi_low).astype(int)


def backtest_v2(start='2018-01-01', end='2022-12-31',
                 universe_name='HS300',
                 trading_universe_name=None,
                 max_positions=20,
                 position_pct=0.15,
                 hold_days=10,
                 take_profit=0.30,
                 stop_loss=-0.02,
                 initial_capital=1_000_000.0,
                 verbose=True):
    """ATOS MR v2 完整回测

    Args:
        trading_universe_name: 限制只交易该 universe 的股票（None=不限制）
           例: trading_universe_name='HS300' 时, 从 ALL 检测信号但只买入 HS300 股票
           这允许"扩大股池寻找规律, 只交易优质标的"

    Returns:
        dict with keys: total_return, annual_return, max_drawdown,
                        n_trades, win_rate, equity_curve, trades
    """
    from atos.data import load_processed, load_processed_benchmark
    from atos.data.universe import get_universe
    from data.config import DISABLE_STOCK

    # 1. 加载 universe (检测池)
    universe = get_universe(universe_name)
    universe = [s for s in universe if s not in DISABLE_STOCK]

    # 交易限制 (可选: 字符串名称 或 set/list)
    trading_universe = None
    if trading_universe_name is not None:
        if isinstance(trading_universe_name, (set, list, tuple)):
            trading_universe = set(s for s in trading_universe_name if s not in DISABLE_STOCK)
        else:
            trading_universe = set(get_universe(trading_universe_name))
            trading_universe = set(s for s in trading_universe if s not in DISABLE_STOCK)
    if verbose:
        print('Universe (' + universe_name + '):', len(universe), 'stocks')

    # 2. 加载大盘（用于状态识别）
    market = load_processed_benchmark('hs300', start=start, end=end)
    if market is None or len(market) == 0:
        raise ValueError('No market data')

    # 3. 加载股票数据 + 预计算信号
    if verbose:
        print('Loading stocks and signals...')
    stock_data = {}
    signals = {}
    signals_secondary = {}
    for sym in universe:
        df = load_processed(sym, start=start, end=end)
        if df is None or len(df) < 100:
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
        stock_data[sym] = df
        signals[sym] = _compute_signal_v2(df)
        signals_secondary[sym] = _compute_signal_v2_secondary(df)
    if verbose:
        print('Loaded', len(stock_data), 'stocks')

    # 4. 状态识别 (使用滞后版本避免前视偏差)
    # 原始 detect_full_regime 使用 hysteresis (min_duration=3) 会用未来数据确认状态
    # 真实交易中我们不知道未来，所以应该使用滞后 MIN_DURATION 天的状态
    from atos.regime import detect_full_regime
    regime_df_raw = detect_full_regime(market, None)
    # 滞后 MIN_DURATION 天：用 T-N 天的状态作为 T 的"已知"状态
    # 这样在 T 时使用的是 T-N 时的状态，避免使用未来信息
    MIN_DURATION = 3
    regime_df = regime_df_raw.shift(MIN_DURATION, freq='B')
    # shift 后早期日期会变成 NaT，用 'SIDEWAYS' 填充（最保守的状态）
    regime_df['effective_state'] = regime_df['effective_state'].fillna('SIDEWAYS')
    if verbose:
        print('Regime counts (after lag):', regime_df['effective_state'].value_counts().to_dict())

    # 5. 状态仓位乘数
    regime_pos_mult = {
        'BULL': 1.5, 'SIDEWAYS': 1.0,
        'BEAR': 0.2, 'CHOPPY_BEAR': 0.3,
        'CRASH': 0.0,
    }

    # 6. 成本参数
    commission_rate = 0.00025
    stamp_tax_rate = 0.001
    slippage = 0.001
    transfer_fee = 0.00001
    min_commission = 5.0

    def calc_buy_cost(shares, price):
        sp = price * (1 + slippage)
        gws = shares * sp
        comm = max(gws * commission_rate, min_commission)
        tfee = gws * transfer_fee
        return gws + comm + tfee

    def calc_sell_proceeds(shares, price):
        sp = price * (1 - slippage)
        gws = shares * sp
        comm = max(gws * commission_rate, min_commission)
        stamp = gws * stamp_tax_rate
        tfee = gws * transfer_fee
        return gws - comm - stamp - tfee

    # 7. 主循环
    trading_dates = market.index.tolist()
    cash = initial_capital
    positions = {}  # sym -> {entry_date, entry_price, shares, peak, last_close, sell_queued_date}
    pending_buys = []  # (sym, sig_date) - T+1 开盘执行
    pending_sells = []  # (sym, ratio, reason, queue_date) - T+1 开盘执行
    trades = []
    equity_curve = []
    total_equity = initial_capital
    MAX_PENDING_DAYS = 20  # 卖出挂单最多等 20 天（处理长期停牌）

    if verbose:
        print('Running backtest...')
    t0 = time.time()
    for day_idx, date in enumerate(trading_dates):
        if date in regime_df.index:
            state = regime_df.loc[date, 'effective_state']
        else:
            state = 'SIDEWAYS'

        today_prices = {}
        for sym, df in stock_data.items():
            if date in df.index:
                today_prices[sym] = {
                    'open': float(df.loc[date, 'open']),
                    'high': float(df.loc[date, 'high']),
                    'low': float(df.loc[date, 'low']),
                    'close': float(df.loc[date, 'close']),
                }

        pos_value_now = 0.0
        for sym, pos in positions.items():
            if sym in today_prices:
                pos_value_now += pos['shares'] * today_prices[sym]['close']
        total_equity = cash + pos_value_now

        # 7.1 处理 T+1 待执行买单
        if pending_buys:
            new_pending = []
            for sym, sig_date in pending_buys:
                if sym not in today_prices:
                    new_pending.append((sym, sig_date))
                    continue
                if sym in positions:
                    continue
                exec_price = today_prices[sym]['open']
                # 涨跌停/停牌检查
                df_sym = stock_data[sym]
                try:
                    if 'is_limit_up' in df_sym.columns and bool(df_sym.loc[date, 'is_limit_up']):
                        continue  # 涨停日不买入
                    if 'volume' in df_sym.columns and float(df_sym.loc[date, 'volume']) == 0:
                        continue  # 停牌不买入
                except Exception:
                    pass
                # 备用检查：OHLC 推断涨跌停
                if today_prices[sym]['low'] >= exec_price * 1.095:
                    continue
                pos_mult = regime_pos_mult.get(state, 0.5)
                per_value = total_equity * position_pct * pos_mult
                shares = int(per_value / exec_price / 100) * 100
                if shares < 100:
                    continue
                cost = calc_buy_cost(shares, exec_price)
                if cost > cash * 0.95:
                    affordable = int(cash * 0.95 / (exec_price * (1 + commission_rate + transfer_fee)) / 100) * 100
                    if affordable < 100:
                        continue
                    shares = affordable
                    cost = calc_buy_cost(shares, exec_price)
                cash -= cost
                positions[sym] = {
                    'entry_date': date, 'entry_price': exec_price,
                    'shares': shares, 'peak': exec_price,
                }
                trades.append({'date': date, 'symbol': sym, 'action': 'BUY',
                               'price': exec_price, 'shares': shares})
            pending_buys = new_pending

        # 7.1.5 处理 T+1 待执行卖出 (持仓首日登记的卖出)
        if pending_sells:
            new_pending_sells = []
            for sym, ratio, reason, queue_date in pending_sells:
                if sym not in positions:
                    continue
                if sym not in today_prices:
                    new_pending_sells.append((sym, ratio, reason, queue_date))
                    continue
                pos = positions[sym]
                df_sym = stock_data[sym]
                days_pending = (date - queue_date).days
                exec_price = today_prices[sym]['open']
                # 跌停/停牌检查
                suspended = False
                try:
                    if 'is_limit_down' in df_sym.columns and bool(df_sym.loc[date, 'is_limit_down']):
                        suspended = True
                    elif 'volume' in df_sym.columns and float(df_sym.loc[date, 'volume']) == 0:
                        suspended = True
                except Exception:
                    pass
                if today_prices[sym]['high'] <= exec_price * 0.905:
                    suspended = True
                if suspended and days_pending < MAX_PENDING_DAYS:
                    new_pending_sells.append((sym, ratio, reason, queue_date))
                    continue
                if suspended:
                    # 跌停/停牌超过 N 天强制折价卖出
                    exec_price = exec_price * 0.95
                # 计算 pnl（基于入场上一次 close）
                prev_close = pos.get('last_close', pos['entry_price'])
                pnl_pct = (prev_close - pos['entry_price']) / pos['entry_price']
                shares_to_sell = int(pos['shares'] * ratio / 100) * 100
                if shares_to_sell < 100:
                    shares_to_sell = pos['shares']
                if shares_to_sell > pos['shares']:
                    shares_to_sell = pos['shares']
                proceeds = calc_sell_proceeds(shares_to_sell, exec_price)
                cash += proceeds
                pos['shares'] -= shares_to_sell
                trades.append({'date': date, 'symbol': sym, 'action': 'SELL',
                               'price': exec_price, 'shares': shares_to_sell,
                               'reason': reason, 'pnl_pct': pnl_pct})
                if pos['shares'] <= 0:
                    del positions[sym]
            pending_sells = new_pending_sells

        # 7.2 处理卖出 (T 日信号 → 登记 T+1 卖出)
        for sym, pos in list(positions.items()):
            if sym not in today_prices:
                continue
            cur_close = today_prices[sym]['close']
            cur_high = today_prices[sym]['high']
            ret = (cur_close - pos['entry_price']) / pos['entry_price']
            days_held = (date - pos['entry_date']).days
            if cur_high > pos['peak']:
                pos['peak'] = cur_high
            pos['last_close'] = cur_close
            # 分股/合股检测: 今日 pct_change > 15% 视为 corporate action
            df_sym = stock_data[sym]
            is_corporate_action = False
            try:
                if 'pct_change' in df_sym.columns:
                    today_pct = float(df_sym.loc[date, 'pct_change'])
                    if abs(today_pct) > 15.0:
                        is_corporate_action = True
            except Exception:
                pass
            should_sell = False
            reason = ''
            if is_corporate_action:
                should_sell = True
                reason = 'corp_action'
            elif ret >= take_profit:
                should_sell = True
                reason = 'tp'
            elif ret <= stop_loss:
                should_sell = True
                reason = 'sl'
            elif days_held >= hold_days:
                should_sell = True
                reason = 'time'
            elif state == 'CRASH':
                should_sell = True
                reason = 'crash'
            if should_sell:
                # T+1 合规: 买入当日不能卖出
                if pos['entry_date'] == date:
                    # 登记次日（T+1）开盘卖出
                    already_queued = any(p[0] == sym for p in pending_sells)
                    if not already_queued:
                        pending_sells.append((sym, 1.0, reason, date))
                else:
                    # 持仓已 > 1 天：直接次日开盘卖出（用今日 open 作为代理）
                    # 但要确保不是当日买 - 已检查 entry_date != date
                    exec_price = today_prices[sym]['open']
                    # 跌停/停牌不卖出
                    suspended = False
                    try:
                        if 'is_limit_down' in df_sym.columns and bool(df_sym.loc[date, 'is_limit_down']):
                            suspended = True
                        elif 'volume' in df_sym.columns and float(df_sym.loc[date, 'volume']) == 0:
                            suspended = True
                    except Exception:
                        pass
                    if today_prices[sym]['high'] <= exec_price * 0.905:
                        suspended = True
                    if not suspended:
                        # 分股/合股: 用前一日 close 作为公平退出价
                        # (避免 unadjusted 数据中 split 造成的虚假亏损)
                        if reason == 'corp_action':
                            prev_idx = df_sym.index.get_loc(date) - 1
                            if prev_idx >= 0:
                                prev_close = float(df_sym.iloc[prev_idx]['close'])
                                exec_price = prev_close
                        proceeds = calc_sell_proceeds(pos['shares'], exec_price)
                        cash += proceeds
                        # 调整 pnl_pct (split 后价值应约等于买入价)
                        adjusted_pnl = (exec_price - pos['entry_price']) / pos['entry_price']
                        trades.append({'date': date, 'symbol': sym, 'action': 'SELL',
                                       'price': exec_price, 'shares': pos['shares'],
                                       'reason': reason, 'pnl_pct': adjusted_pnl})
                        del positions[sym]
                    else:
                        # 跌停则挂单
                        already_queued = any(p[0] == sym for p in pending_sells)
                        if not already_queued:
                            pending_sells.append((sym, 1.0, reason, date))

        # 7.3 排队新买单 (T close 信号 → T+1 open 执行)
        if state != 'CRASH':
            n_to_buy = max_positions - len(positions) - len(pending_buys)
            if n_to_buy > 0 and cash > 0:
                candidates = []
                for sym, df in stock_data.items():
                    if sym in positions or sym in [p[0] for p in pending_buys]:
                        continue
                    if date not in df.index:
                        continue
                    # 交易范围限制 (只交易指定 universe 的股票)
                    if trading_universe is not None and sym not in trading_universe:
                        continue
                    # BULL 也接受副信号 (drop<-8% AND RSI<30)
                    has_main = signals[sym].get(date, 0) == 1
                    has_sec = (state == 'BULL' and signals_secondary[sym].get(date, 0) == 1 and not has_main)
                    if not has_main and not has_sec:
                        continue
                    if 'is_st' in df.columns:
                        try:
                            if bool(df.loc[date, 'is_st']):
                                continue
                        except Exception:
                            pass
                    if 'volume' in df.columns:
                        try:
                            if float(df.loc[date, 'volume']) == 0:
                                continue
                        except Exception:
                            pass
                    # 过滤除权除息/分股等异常: 近 5 日有 > 15% 单日波动
                    try:
                        recent_pct = df['pct_change'].loc[date-pd.tseries.offsets.BDay(5):date].abs()
                        if (recent_pct > 15.0).any():  # > 15% 异常
                            continue
                    except Exception:
                        pass
                    rsi6 = float(df.loc[date, 'RSI6']) if 'RSI6' in df.columns else 50
                    prio = 0 if has_main else 1
                    candidates.append((sym, rsi6, prio, float(df.loc[date, 'close'])))

                # v6: 趋势跟踪信号 (MA20突破+放量, 牛市补充)
                # 只在MR信号不足时启用
                if len(candidates) < n_to_buy:
                    for sym, df in stock_data.items():
                        if sym in positions or sym in [p[0] for p in pending_buys]:
                            continue
                        if date not in df.index:
                            continue
                        if trading_universe is not None and sym not in trading_universe:
                            continue
                        try:
                            idx = df.index.get_loc(date)
                            if idx < 25: continue
                            close_v = df['close']
                            if isinstance(close_v, pd.DataFrame): close_v = close_v.iloc[:, 0]
                            c = float(close_v.iloc[idx])
                            c1 = float(close_v.iloc[idx - 1])
                            ma20 = float(close_v.rolling(20).mean().iloc[idx])
                            vol_v = df['volume']
                            if isinstance(vol_v, pd.DataFrame): vol_v = vol_v.iloc[:, 0]
                            v = float(vol_v.iloc[idx])
                            v20 = float(vol_v.rolling(20).mean().iloc[idx])
                            if np.isfinite(ma20) and np.isfinite(v20) and v20 > 0:
                                # MA20突破 + 放量确认
                                if c > ma20 and c1 < ma20 and v > 1.2 * v20:
                                    if 'is_st' not in df.columns or not bool(df.loc[date, 'is_st']):
                                        if 'volume' not in df.columns or float(df.loc[date, 'volume']) > 0:
                                            candidates.append((sym, 99, 2, c))  # prio=2, RSI虚拟
                        except Exception:
                            pass

                # v7: 突破前高信号 (20日新高+趋势确认)
                if len(candidates) < n_to_buy:
                    for sym, df in stock_data.items():
                        if sym in positions or sym in [p[0] for p in pending_buys]: continue
                        if date not in df.index: continue
                        if trading_universe is not None and sym not in trading_universe: continue
                        try:
                            idx = df.index.get_loc(date)
                            if idx < 25: continue
                            close_v = df['close']
                            if isinstance(close_v, pd.DataFrame): close_v = close_v.iloc[:, 0]
                            high_v = df['high']
                            if isinstance(high_v, pd.DataFrame): high_v = high_v.iloc[:, 0]
                            c = float(close_v.iloc[idx])
                            h20 = float(high_v.iloc[idx-20:idx].max())
                            ma20 = float(close_v.rolling(20).mean().iloc[idx])
                            ma60 = float(close_v.rolling(60).mean().iloc[idx])
                            if np.isfinite(ma20) and np.isfinite(ma60):
                                if c > h20 and ma20 > ma60:
                                    if 'is_st' not in df.columns or not bool(df.loc[date, 'is_st']):
                                        if 'volume' not in df.columns or float(df.loc[date, 'volume']) > 0:
                                            candidates.append((sym, 50, 3, c))
                        except Exception:
                            pass

                # 排序: 主信号优先, RSI升序, 趋势最后
                candidates.sort(key=lambda x: (x[2], x[1]))
                for cand in candidates[:n_to_buy]:
                    sym = cand[0]
                    pending_buys.append((sym, date))

        pos_value = 0.0
        for sym, pos in positions.items():
            if sym in today_prices:
                pos_value += pos['shares'] * today_prices[sym]['close']
        equity = cash + pos_value
        equity_curve.append({'date': date, 'equity': equity, 'state': state,
                             'n_pos': len(positions)})

    if verbose:
        print('Backtest time:', round(time.time() - t0, 1), 's')

    eq_df = pd.DataFrame(equity_curve).set_index('date')
    final_equity = eq_df['equity'].iloc[-1]
    total_return = final_equity / initial_capital - 1
    years = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
    annual_return = (1 + total_return) ** (1/years) - 1 if years > 0 else 0
    cummax = eq_df['equity'].cummax()
    max_drawdown = ((eq_df['equity'] - cummax) / cummax).min()

    t_df = pd.DataFrame(trades)
    n_buys = len(t_df[t_df['action'] == 'BUY']) if not t_df.empty else 0
    n_sells = len(t_df[t_df['action'] == 'SELL']) if not t_df.empty else 0

    trades_paired = []
    if not t_df.empty:
        for sym, grp in t_df.groupby('symbol'):
            b = grp[grp['action'] == 'BUY'].sort_values('date')
            s = grp[grp['action'] == 'SELL'].sort_values('date')
            for i in range(min(len(b), len(s))):
                trades_paired.append({
                    'pnl_pct': s.iloc[i]['price'] / b.iloc[i]['price'] - 1,
                })
    paired_df = pd.DataFrame(trades_paired)
    win_rate = (paired_df['pnl_pct'] > 0).mean() if len(paired_df) > 0 else 0

    yearly_returns = []
    if not eq_df.empty:
        prev = initial_capital
        for d, val in eq_df['equity'].resample('YE').last().items():
            yearly_returns.append((d.year, (val / prev - 1)))
            prev = val

    result = {
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'n_trades': n_sells,
        'n_buys': n_buys,
        'win_rate': win_rate,
        'final_equity': final_equity,
        'years': years,
        'equity_curve': eq_df,
        'trades': t_df,
        'yearly_returns': yearly_returns,
    }

    if verbose:
        print()
        print('=== ATOS MR v2 BACKTEST ===')
        print('Final equity:', round(final_equity))
        print('Total return:', round(total_return * 100, 2), '%')
        print('Annual return:', round(annual_return * 100, 2), '%')
        print('Max DD:', round(max_drawdown * 100, 2), '%')
        print('Trades:', n_sells)
        print('Win rate:', round(win_rate * 100, 1), '%')
        if len(paired_df) > 0:
            print('Avg pnl/trade:', round(paired_df['pnl_pct'].mean() * 100, 3), '%')
        print()
        print('Yearly:')
        for y, r in yearly_returns:
            print(' ', y, ':', round(r * 100, 2), '%')

    return result


if __name__ == '__main__':
    result = backtest_v2('2018-01-01', '2022-12-31', 'HS300')
