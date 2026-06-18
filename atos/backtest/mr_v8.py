"""ATOS MR v8: 相对排名 + 自适应参数 (跨平台鲁棒)

核心改进:
1. 入场: 全市场排名 (drop_5d z-score + RSI6 逆 z-score), 取前N
2. 止损: ATR自适应 (SL = -ATR_pct × k, 默认k=1.0)
3. 持仓: 波动率自适应 (hd = base + vol_ratio × adj)
4. 选股: 按得分排序, 不再按代码顺序
"""
import pandas as pd
import numpy as np
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK


def _get_series(df, col):
    val = df[col]
    if isinstance(val, pd.DataFrame): return val.iloc[:, 0]
    return val


def _compute_relative_scores(stock_data, date, trading_universe=None):
    """在每个交易日对全市场做相对排名 (跨平台鲁棒)

    返回: {symbol: (score, drop_5d, RSI6, close)}
    得分越低越超卖(越好)
    """
    scores = {}
    for sym, df in stock_data.items():
        if trading_universe and sym not in trading_universe:
            continue
        if date not in df.index:
            continue
        try:
            idx = df.index.get_loc(date)
            if idx < 10:
                continue
            close = _get_series(df, 'close')
            rsi6 = _get_series(df, 'RSI6')
            c = float(close.iloc[idx])
            c5 = float(close.iloc[idx - 5])
            drop = c / c5 - 1
            rsi = float(rsi6.iloc[idx])
            if not np.isfinite(drop) or not np.isfinite(rsi):
                continue
            # 过滤 ST/停牌 + 绝对底线(避免牛市买所有)
            if 'is_st' in df.columns and bool(df.loc[date, 'is_st']):
                continue
            if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0:
                continue
            if drop > -0.03 or rsi > 50:  # 至少轻微超卖
                continue
            scores[sym] = (drop, rsi, c)
        except Exception:
            continue

    if len(scores) < 20:
        return {}

    # 计算 z-score
    drops = np.array([v[0] for v in scores.values()])
    rsis = np.array([v[1] for v in scores.values()])
    drop_mean = drops.mean()
    drop_std = drops.std() if drops.std() > 0 else 0.01
    rsi_mean = rsis.mean()
    rsi_std = rsis.std() if rsis.std() > 0 else 0.01

    # 排名得分: drop越低越好 + RSI越低越好
    ranked = {}
    for sym, (drop, rsi, c) in scores.items():
        drop_z = (drop - drop_mean) / drop_std  # 负值=超跌
        rsi_z = (rsi - rsi_mean) / rsi_std      # 负值=超卖
        score = drop_z * 0.6 + rsi_z * 0.4       # 综合分, 越低越好
        atr_val = None
        try:
            atr_v = _get_series(stock_data[sym], 'ATR')
            atr_val = float(atr_v.iloc[stock_data[sym].index.get_loc(date)]) / c
        except Exception:
            pass
        ranked[sym] = (score, drop, rsi, c, atr_val)

    return ranked


def backtest_v8(start='2018-01-01', end='2022-12-31',
                universe_name='ALL', trading_universe_name=None,
                top_n=25, position_pct=0.15, base_hold=10,
                atr_sl_k=1.0, initial_capital=1000000.0, verbose=True):
    """v8回测: 相对排名 + 自适应参数"""
    universe = get_universe(universe_name)
    universe = [s for s in universe if s not in DISABLE_STOCK]
    trading_universe = None
    if trading_universe_name is not None:
        if isinstance(trading_universe_name, (set, list)):
            trading_universe = set(trading_universe_name)
        else:
            trading_universe = set(get_universe(trading_universe_name))
        trading_universe = set(s for s in trading_universe if s not in DISABLE_STOCK)
    if verbose:
        td_count = len(trading_universe) if trading_universe else len(universe)
        print('Detect:', len(universe), '| Trade:', td_count)

    market = load_processed_benchmark('hs300', start=start, end=end)
    mc = market['close']
    mma20 = mc.rolling(20).mean()
    mma60 = mc.rolling(60).mean()
    # Market volatility (20d)
    m_vol = mc.pct_change().rolling(20).std() * np.sqrt(252)
    median_vol = m_vol.median()

    if verbose: print('Loading stocks...')
    stock_data = {}
    for sym in universe:
        try:
            df = load_processed(sym, start=start, end=end)
            if df is not None and len(df) > 100:
                stock_data[sym] = df
        except Exception: continue
    if verbose: print('Loaded:', len(stock_data))

    cash = initial_capital
    positions = {}
    pending_buys = []
    pending_sells = []
    equity_curve = []
    total_equity = initial_capital
    MAX_PENDING = 20
    CORP_TH = 0.15
    dates = market.index.tolist()

    def calc_cost(shares, price, is_buy=True):
        if is_buy: return shares * price * 1.001 * 1.00026
        else: return shares * price * 0.999 * 0.99875

    for date in dates:
        # === T+1 buys ===
        new_pb = []
        for sym, sig_c, sig_score in pending_buys:
            if sym not in stock_data or date not in stock_data[sym].index: continue
            if sym in positions: continue
            df = stock_data[sym]
            try:
                if 'is_limit_up' in df.columns and bool(df.loc[date, 'is_limit_up']): continue
                if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0: continue
            except: pass
            try:
                exec_price = float(df.loc[date, 'open'])
            except: continue
            # ATR-based SL
            try:
                atr_v = float(_get_series(df, 'ATR').loc[date])
                if np.isnan(atr_v) or atr_v <= 0: atr_v = exec_price * 0.03
            except: atr_v = exec_price * 0.03
            stop_dist = atr_sl_k * atr_v
            if stop_dist <= 0: stop_dist = exec_price * 0.05
            # Position size
            per_value = total_equity * position_pct
            shares = int(per_value / (exec_price * 1.001) / 100) * 100
            if shares < 100: continue
            cost = calc_cost(shares, exec_price, True)
            if cost > cash * 0.95:
                shares = int(cash * 0.95 / (exec_price * 1.001) / 100) * 100
                if shares < 100: continue
                cost = calc_cost(shares, exec_price, True)
            cash -= cost
            positions[sym] = {'entry_date': date, 'entry_price': exec_price,
                             'shares': shares, 'peak': exec_price,
                             'stop_price': exec_price - stop_dist,
                             'atr': atr_v, 'score': sig_score}
        pending_buys = new_pb

        # === T+1 sells ===
        new_ps = []
        for sym, ratio, reason, queue_date in pending_sells:
            if sym not in positions: continue
            if sym not in stock_data or date not in stock_data[sym].index: continue
            df = stock_data[sym]
            blocked = False
            try:
                if 'is_limit_down' in df.columns and bool(df.loc[date, 'is_limit_down']): blocked = True
                if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0: blocked = True
            except: pass
            if blocked:
                if (date - queue_date).days < MAX_PENDING:
                    new_ps.append((sym, ratio, reason, queue_date))
                    continue
                exec_price = float(df.loc[date, 'open']) * 0.95
            else:
                try: exec_price = float(df.loc[date, 'open'])
                except: continue
            pos = positions[sym]
            if reason == 'corp_action':
                try:
                    pi = df.index.get_loc(date) - 1
                    if pi >= 0: exec_price = float(df.iloc[pi]['close'])
                except: pass
            proceeds = calc_cost(pos['shares'], exec_price, False)
            cash += proceeds
            del positions[sym]
        pending_sells = new_ps

        # === Entry signals (相对排名) ===
        held = set(positions.keys())
        pb = set(s for s, _, _ in pending_buys)
        # 市场宽度
        if date in mma20.index:
            breadth = (mc.loc[date] > mma20.loc[date] if date in mc.index else False)
        else: breadth = False
        dyn_top_n = int(top_n * 1.2) if breadth else top_n

        n_to_buy = dyn_top_n - len(positions) - len(pending_buys)
        if n_to_buy > 0 and cash > 10000:
            ranked = _compute_relative_scores(stock_data, date, trading_universe)
            if ranked:
                # 按得分升序 (越超卖越靠前)
                sorted_ranked = sorted(ranked.items(), key=lambda x: x[1][0])
                for sym, (score, drop, rsi, c, atr_v) in sorted_ranked[:n_to_buy]:
                    pending_buys.append((sym, c, score))

        # === Exit signals ===
        today = date
        # 动态hold: 基于市场波动
        if date in m_vol.index:
            cur_vol = m_vol.loc[date]
            if not np.isnan(cur_vol) and median_vol > 0:
                vol_ratio = cur_vol / median_vol
                dyn_hold = int(base_hold * (0.7 + 0.3 * vol_ratio))
            else: dyn_hold = base_hold
        else: dyn_hold = base_hold

        for sym, pos in list(positions.items()):
            if pos['entry_date'] == today: continue
            try:
                cur_close = float(stock_data[sym].loc[today, 'close'])
                cur_high = float(stock_data[sym].loc[today, 'high'])
            except: continue
            if cur_close <= 0: continue
            if cur_high > pos['peak']: pos['peak'] = cur_high
            # ATR trailing stop update
            try:
                cur_atr = float(_get_series(stock_data[sym], 'ATR').loc[today])
                if np.isfinite(cur_atr) and cur_atr > 0:
                    pos['atr'] = cur_atr
                    pos['stop_price'] = max(pos.get('stop_price', 0),
                                           pos['peak'] - atr_sl_k * cur_atr)
            except: pass
            ret = cur_close / pos['entry_price'] - 1
            days_held = (today - pos['entry_date']).days
            is_corp = False
            try:
                pct = float(stock_data[sym].loc[today, 'pct_change'])
                if not np.isnan(pct) and abs(pct) > CORP_TH * 100: is_corp = True
            except: pass

            should_sell = False; reason = ''
            if is_corp: should_sell = True; reason = 'corp_action'
            elif days_held >= dyn_hold: should_sell = True; reason = 'time'
            elif cur_close < pos.get('stop_price', 0): should_sell = True; reason = 'trail'
            if should_sell:
                if not any(p[0] == sym for p in pending_sells):
                    pending_sells.append((sym, 1.0, reason, today))

        # === Equity ===
        pv = 0
        for sym, pos in positions.items():
            try:
                if date in stock_data[sym].index:
                    pv += pos['shares'] * float(stock_data[sym].loc[date, 'close'])
            except: pass
        equity = cash + pv
        total_equity = equity
        equity_curve.append({'date': date, 'equity': equity, 'n_pos': len(positions)})

    eq_df = pd.DataFrame(equity_curve).set_index('date')
    final = eq_df['equity'].iloc[-1]
    total_ret = final / initial_capital - 1
    yrs = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
    ann_ret = (1 + total_ret) ** (1 / yrs) - 1 if yrs > 0 else 0
    dd = ((eq_df['equity'] - eq_df['equity'].cummax()) / eq_df['equity'].cummax()).min()
    yearly = []
    prev = initial_capital
    for d, val in eq_df['equity'].resample('YE').last().items():
        yearly.append((d.year, val / prev - 1)); prev = val

    if verbose:
        print('=== ATOS MR v8 ===')
        print('Annual: +' + str(round(ann_ret * 100, 2)) + '%  DD: -' + str(round(abs(dd) * 100, 2)) + '%')
        for y, r in yearly: print('  ' + str(y) + ': ' + str(round(r * 100, 1)) + '%')

    return {'annual_return': ann_ret, 'total_return': total_ret,
            'max_drawdown': dd, 'final_equity': final,
            'equity_curve': eq_df, 'yearly_returns': yearly}


if __name__ == '__main__':
    from atos.data.universe import get_universe
    h = get_universe('HS300'); c = get_universe('CYB_STAR_50')
    s352 = set(s for s in set(h) | set(c) if s not in DISABLE_STOCK)
    backtest_v8('2018-01-01', '2022-12-31', 'ALL', trading_universe_name=s352)
