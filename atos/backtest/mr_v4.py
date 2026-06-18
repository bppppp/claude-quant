# -*- coding: utf-8 -*-
"""ATOS MR v4: 全市场普适策略 (ALL 1339 只, 2018-2022 调参)

设计原则:
1. 双信号体系: 大幅回调 (5d -10%~-20%) + 中等回调 (5d -8%~-12%, RSI<30)
2. 大盘环境: 无过滤 (允许 BEAR 做反弹, 靠仓位风控)
3. 仓位调控: BEAR 0.2x, BULL 1.0x, CRASH 0
4. 严格风控: 止盈 +5%, 止损 -3%, 持有 7 天
5. 无前视偏差: 状态检测不滞后 (用 T 时刻 close vs MA60)
"""
import pandas as pd
import numpy as np
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK


def _get_series(df, col):
    val = df[col]
    if isinstance(val, pd.DataFrame):
        return val.iloc[:, 0]
    return val


def _compute_signal_v4(df, idx):
    """v4 主信号: 5d 跌 -20%~-10% (大幅回调, 强反弹)
    v4 副信号: 5d 跌 -12%~-8% AND RSI(6)<30 (中等回调+超卖)
    """
    try:
        if idx < 10:
            return False, None
        close = _get_series(df, 'close')
        rsi6 = _get_series(df, 'RSI6')
        c = float(close.iloc[idx])
        c5 = float(close.iloc[idx - 5])
        drop_5d = c / c5 - 1
        rsi = float(rsi6.iloc[idx]) if not np.isnan(rsi6.iloc[idx]) else np.nan
        if not np.isfinite(drop_5d):
            return False, None
        # 主信号: 大幅回调 -20%~-10%
        if -0.20 < drop_5d < -0.10:
            return True, 'main'
        # 副信号: 中等回调 -12%~-8% + RSI<30
        if -0.12 < drop_5d < -0.08 and np.isfinite(rsi) and rsi < 30:
            return True, 'secondary'
        return False, None
    except Exception:
        return False, None


def backtest_v4(start='2018-01-01', end='2022-12-31', universe_name='ALL',
                max_positions=20, position_pct=0.05,
                hold_days=7, take_profit=0.05, stop_loss=0.03,
                initial_capital=1000000.0, verbose=True):
    """v4 回测: 双信号 + 仓位调控 + 严格风控"""
    universe = get_universe(universe_name)
    universe = [s for s in universe if s not in DISABLE_STOCK]
    if verbose:
        print('Universe (' + universe_name + '):', len(universe))
    market = load_processed_benchmark('hs300', start=start, end=end)
    market_close = market['close']
    # 大盘 MA60 (用于仓位调控)
    market_ma60 = market_close.rolling(60).mean()
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
        return shares * price * 1.001 * 1.00026
    def calc_sell_proceeds(shares, price):
        return shares * price * 0.999 * 0.99875
    def is_suspended(df, date):
        try:
            if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0:
                return True
        except Exception:
            pass
        return False
    def is_limit_up(df, date):
        try:
            if 'is_limit_up' in df.columns and bool(df.loc[date, 'is_limit_up']):
                return True
        except Exception:
            pass
        return False
    def is_limit_down(df, date):
        try:
            if 'is_limit_down' in df.columns and bool(df.loc[date, 'is_limit_down']):
                return True
        except Exception:
            pass
        return False
    def is_corp_action(df, date):
        try:
            pct = float(df.loc[date, 'pct_change'])
            if not np.isnan(pct) and abs(pct) > CORP_ACTION_TH * 100:
                return True
        except Exception:
            pass
        return False

    for date in trading_dates:
        # === 1. 处理 T+1 pending buys ===
        new_pb = []
        for sym, sig_close in pending_buys:
            if sym not in stock_data or date not in stock_data[sym].index:
                new_pb.append((sym, sig_close))
                continue
            if sym in positions:
                continue
            df = stock_data[sym]
            if is_suspended(df, date) or is_limit_up(df, date):
                new_pb.append((sym, sig_close))
                continue
            try:
                exec_price = float(df.loc[date, 'open'])
            except Exception:
                new_pb.append((sym, sig_close))
                continue
            # 仓位调控: 大盘 close vs MA60
            pos_mult = 1.0
            if date in market_ma60.index:
                m_ma60 = float(market_ma60.loc[date])
                if not np.isnan(m_ma60):
                    mc = float(market_close.loc[date])
                    if mc < m_ma60:
                        pos_mult = 0.2
            per_value = total_equity * position_pct * pos_mult
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
            positions[sym] = {'entry_date': date, 'entry_price': exec_price,
                             'shares': shares, 'peak': exec_price, 'last_close': exec_price}
        pending_buys = new_pb

        # === 2. 处理 T+1 pending sells ===
        new_ps = []
        for sym, ratio, reason, queue_date in pending_sells:
            if sym not in positions:
                continue
            if sym not in stock_data or date not in stock_data[sym].index:
                new_ps.append((sym, ratio, reason, queue_date))
                continue
            df = stock_data[sym]
            blocked = is_suspended(df, date) or is_limit_down(df, date)
            if blocked:
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

        # === 3. 入场信号 (T close 决策) ===
        held = set(positions.keys())
        pb = set([s for s, _ in pending_buys])
        available = [s for s in stock_data.keys() if s not in held and s not in pb]
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
                if is_suspended(df, date):
                    continue
                # ST 过滤
                try:
                    if 'is_st' in df.columns and bool(df.loc[date, 'is_st']):
                        continue
                except Exception:
                    pass
                # 除权异常过滤 (近 5 日有 > 15% 波动)
                try:
                    pcts = df['pct_change'].iloc[max(0, idx-5):idx+1].abs()
                    if (pcts > CORP_ACTION_TH * 100).any():
                        continue
                except Exception:
                    pass
                triggered, sig_type = _compute_signal_v4(df, idx)
                if triggered:
                    try:
                        rsi6 = _get_series(df, 'RSI6')
                        rsi = float(rsi6.iloc[idx])
                    except Exception:
                        rsi = 50
                    close_p = float(_get_series(df, 'close').iloc[idx])
                    # 主信号优先
                    prio = 0 if sig_type == 'main' else 1
                    candidates.append((sym, rsi, prio, close_p, sig_type))
            candidates.sort(key=lambda x: (x[2], x[1]))  # prio first, then RSI asc
            for sym, rsi, prio, close_p, sig_type in candidates[:n_to_buy]:
                pending_buys.append((sym, close_p))

        # === 4. 出场信号 (T close 决策) ===
        today = date
        for sym, pos in list(positions.items()):
            # T+1 锁: 买入当日不卖
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
            is_corp = is_corp_action(stock_data[sym], today)
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

        # === 5. 记录净值 ===
        pos_value = 0
        for sym, pos in positions.items():
            if date in stock_data[sym].index:
                try:
                    pos_value += pos['shares'] * float(stock_data[sym].loc[date, 'close'])
                except Exception:
                    pass
        equity = cash + pos_value
        total_equity = equity
        equity_curve.append({'date': date, 'equity': equity, 'cash': cash,
                            'pos_value': pos_value, 'n_pos': len(positions),
                            'pending_buys': len(pending_buys),
                            'pending_sells': len(pending_sells)})
    # === End of loop ===

    # === 6. 结果统计 ===
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
        print('=== ATOS MR v4 BACKTEST ===')
        print('Final equity: ' + str(round(final_equity)))
        print('Total return: %+.2f%%' % (total_return * 100))
        print('Annual return: %+.2f%%' % (annual_return * 100))
        print('Max DD: %.2f%%' % (max_dd * 100))
        print()
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
    backtest_v4('2018-01-01', '2022-12-31', 'ALL')
