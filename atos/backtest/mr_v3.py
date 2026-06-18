# -*- coding: utf-8 -*-
"""ATOS MR v3: 基于 A 股结构性规律的新策略

设计原则 (避免过拟合 2018-2022):
1. 大盘环境过滤: 只在牛市 (close > MA60, 滞后 3 天) 交易
2. 中等回调信号: 5 日跌 5-10% (非极端, 有适度频率)
3. RSI 温和超卖: RSI(6) 10-20 (避开极端, 避开非超卖)
4. 严格风控: 止盈 +5%, 止损 -3%
5. 适度持仓: 单只 5%, 最多 20 只
"""
import pandas as pd
import numpy as np


def _get_series(df, col):
    val = df[col]
    if isinstance(val, pd.DataFrame):
        return val.iloc[:, 0]
    return val


def _compute_signal_v3(df, market_state_series, idx):
    try:
        if idx < 10:
            return False, None
        date = df.index[idx]
        if date in market_state_series.index:
            state = market_state_series.loc[date]
            if state != 'BULL':
                return False, None
        close = _get_series(df, 'close')
        rsi6 = _get_series(df, 'RSI6')
        c = float(close.iloc[idx])
        c5 = float(close.iloc[idx - 5])
        drop_5d = c / c5 - 1
        rsi = float(rsi6.iloc[idx])
        if not np.isfinite(rsi) or not np.isfinite(drop_5d):
            return False, None
        if -0.10 < drop_5d < -0.05 and 10 < rsi < 20:
            return True, 'main'
        return False, None
    except Exception:
        return False, None


def detect_market_state(market_df, lag_days=3):
    close = market_df['close']
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    shifted_c = close.shift(lag_days)
    shifted_ma20 = ma20.shift(lag_days)
    shifted_ma60 = ma60.shift(lag_days)
    state = pd.Series('BEAR', index=close.index, dtype=object)
    crash_5d = close / close.shift(5) - 1
    crash_20d = close / close.shift(20) - 1
    is_crash = (crash_5d.shift(lag_days) < -0.08) | (crash_20d.shift(lag_days) < -0.15)
    is_bull = (shifted_c > shifted_ma20) & (shifted_ma20 > shifted_ma60)
    is_bear = (shifted_c < shifted_ma60)
    state[is_crash.fillna(False)] = 'CRASH'
    state[is_bull.fillna(False) & ~is_crash.fillna(False)] = 'BULL'
    state[is_bear.fillna(False) & ~is_crash.fillna(False)] = 'BEAR'
    state = state.fillna('BEAR')
    return state


def backtest_v3(start='2018-01-01', end='2022-12-31', universe_name='ALL',
                max_positions=20, position_pct=0.05,
                hold_days=7, take_profit=0.05, stop_loss=0.03,
                initial_capital=1000000.0, verbose=True):
    from atos.data import load_processed, load_processed_benchmark
    from atos.data.universe import get_universe
    from data.config import DISABLE_STOCK

    universe = get_universe(universe_name)
    universe = [s for s in universe if s not in DISABLE_STOCK]
    if verbose:
        print('Universe (' + universe_name + '):', len(universe))

    market = load_processed_benchmark('hs300', start=start, end=end)
    market_state = detect_market_state(market, lag_days=3)
    if verbose:
        print('Market state dist:', market_state.value_counts().to_dict())

    if verbose:
        print('Loading stocks...')
    stock_data = {}
    for sym in universe:
        try:
            df = load_processed(sym, start=start, end=end)
            if df is None or len(df) < 100:
                continue
            stock_data[sym] = df
        except Exception:
            continue
    if verbose:
        print('Loaded', len(stock_data))

    cash = initial_capital
    positions = {}
    pending_buys = []
    pending_sells = []
    equity_curve = []
    total_equity = initial_capital
    MAX_PENDING_DAYS = 20
    CORP_ACTION_TH = 0.15

    trading_dates = market.index.tolist()

    def calc_buy_cost(shares, price):
        sp = price * 1.001
        return shares * sp * 1.00026

    def calc_sell_proceeds(shares, price):
        sp = price * 0.999
        return shares * sp * 0.99875

    for date in trading_dates:
        new_pb = []
        for sym, sig_close in pending_buys:
            if sym not in stock_data or date not in stock_data[sym].index:
                continue
            if sym in positions:
                continue
            df = stock_data[sym]
            try:
                date_idx = df.index.get_loc(date)
            except Exception:
                continue
            is_susp = False
            try:
                if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0:
                    is_susp = True
            except Exception:
                pass
            is_lu = False
            try:
                if 'is_limit_up' in df.columns and bool(df.loc[date, 'is_limit_up']):
                    is_lu = True
            except Exception:
                pass
            if is_susp or is_lu:
                new_pb.append((sym, sig_close))
                continue
            try:
                exec_price = float(df.loc[date, 'open'])
            except Exception:
                new_pb.append((sym, sig_close))
                continue
            per_value = total_equity * position_pct
            shares = int(per_value / (exec_price * 1.001) / 100) * 100
            if shares < 100:
                new_pb.append((sym, sig_close))
                continue
            cost = calc_buy_cost(shares, exec_price)
            if cost > cash * 0.95:
                affordable = int(cash * 0.95 / (exec_price * 1.001) / 100) * 100
                if affordable < 100:
                    new_pb.append((sym, sig_close))
                    continue
                shares = affordable
                cost = calc_buy_cost(shares, exec_price)
            cash -= cost
            positions[sym] = {
                'entry_date': date,
                'entry_price': exec_price,
                'shares': shares,
                'peak': exec_price,
                'last_close': exec_price,
            }
        pending_buys = new_pb

        new_ps = []
        for sym, ratio, reason, queue_date in pending_sells:
            if sym not in positions:
                continue
            if sym not in stock_data or date not in stock_data[sym].index:
                continue
            df = stock_data[sym]
            is_susp = False
            try:
                if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0:
                    is_susp = True
            except Exception:
                pass
            is_ld = False
            try:
                if 'is_limit_down' in df.columns and bool(df.loc[date, 'is_limit_down']):
                    is_ld = True
            except Exception:
                pass
            if is_susp or is_ld:
                days_pending = (date - queue_date).days
                if days_pending < MAX_PENDING_DAYS:
                    new_ps.append((sym, ratio, reason, queue_date))
                    continue
                exec_price = float(df.loc[date, 'open']) * 0.95
            else:
                try:
                    exec_price = float(df.loc[date, 'open'])
                except Exception:
                    new_ps.append((sym, ratio, reason, queue_date))
                    continue
            pos = positions[sym]
            if reason == 'corp_action':
                try:
                    prev_idx = df.index.get_loc(date) - 1
                    if prev_idx >= 0:
                        exec_price = float(df.iloc[prev_idx]['close'])
                except Exception:
                    pass
            sell_shares = pos['shares']
            proceeds = calc_sell_proceeds(sell_shares, exec_price)
            cash += proceeds
            del positions[sym]
        pending_sells = new_ps

        held_stocks = set(positions.keys())
        pending_buy_stocks = set([s for s, _ in pending_buys])
        available = [s for s in stock_data.keys()
                     if s not in held_stocks and s not in pending_buy_stocks]
        n_to_buy = max_positions - len(positions) - len(pending_buys)
        if n_to_buy > 0 and cash > 0:
            candidates = []
            for sym in available:
                if date not in stock_data[sym].index:
                    continue
                df = stock_data[sym]
                try:
                    idx = df.index.get_loc(date)
                except Exception:
                    continue
                if idx < 10 or idx >= len(df) - 1:
                    continue
                if date in market_state.index:
                    state = market_state.loc[date]
                    if state != 'BULL':
                        continue
                triggered, sig_type = _compute_signal_v3(df, market_state, idx)
                if triggered:
                    rsi6 = _get_series(df, 'RSI6')
                    rsi = float(rsi6.iloc[idx])
                    candidates.append((sym, rsi, sig_type))
            candidates.sort(key=lambda x: x[1])
            for sym, rsi, sig_type in candidates[:n_to_buy]:
                try:
                    last_price = float(stock_data[sym].loc[date, 'close'])
                except Exception:
                    continue
                pending_buys.append((sym, last_price))

        today = date
        for sym, pos in list(positions.items()):
            if pos['entry_date'] == today:
                try:
                    pos['last_close'] = float(stock_data[sym].loc[today, 'close'])
                except Exception:
                    pos['last_close'] = pos['entry_price']
                continue
            try:
                cur_close = float(stock_data[sym].loc[today, 'close'])
            except Exception:
                continue
            if cur_close <= 0:
                continue
            ret = cur_close / pos['entry_price'] - 1
            days_held = (today - pos['entry_date']).days
            is_corp = False
            try:
                pct = float(stock_data[sym].loc[today, 'pct_change'])
                if not np.isnan(pct) and abs(pct) > CORP_ACTION_TH * 100:
                    is_corp = True
            except Exception:
                pass
            should_sell = False
            reason = ''
            if is_corp:
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
            if should_sell:
                if not any(p[0] == sym for p in pending_sells):
                    pending_sells.append((sym, 1.0, reason, today))
            pos['last_close'] = cur_close

        pos_value = 0
        for sym, pos in positions.items():
            if date in stock_data[sym].index:
                try:
                    pos_value += pos['shares'] * float(stock_data[sym].loc[date, 'close'])
                except Exception:
                    pass
        equity = cash + pos_value
        total_equity = equity
        equity_curve.append({
            'date': date, 'equity': equity,
            'state': market_state.loc[date] if date in market_state.index else 'UNKNOWN',
            'n_pos': len(positions),
        })

    eq_df = pd.DataFrame(equity_curve).set_index('date')
    final_equity = eq_df['equity'].iloc[-1]
    total_return = final_equity / initial_capital - 1
    years = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    cummax = eq_df['equity'].cummax()
    max_dd = ((eq_df['equity'] - cummax) / cummax).min()
    yearly = []
    prev = initial_capital
    for d, val in eq_df['equity'].resample('YE').last().items():
        yearly.append((d.year, val / prev - 1))
        prev = val
    if verbose:
        print()
        print('=== ATOS MR v3 BACKTEST ===')
        print('Final equity:', round(final_equity))
        print('Total return: %+.2f%%' % (total_return * 100))
        print('Annual return: %+.2f%%' % (annual_return * 100))
        print('Max DD: %.2f%%' % (max_dd * 100))
        print('Yearly:')
        for y, r in yearly:
            print('  %d: %+.2f%%' % (y, r * 100))
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'final_equity': final_equity,
        'equity_curve': eq_df,
        'yearly_returns': yearly,
    }


if __name__ == '__main__':
    backtest_v3('2018-01-01', '2022-12-31', 'ALL')
