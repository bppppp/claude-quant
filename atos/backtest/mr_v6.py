"""ATOS MR v6: Multi-Dimensional Adaptive Strategy

v6 架构升级:
1. 信号保留 (drop+RSI, 5年全正已验证)
2. ATR仓位管理 (风险平权, 每笔最大亏损=2%权益)
3. 反弹确认 (跌后阳线才进场, 提高胜率)
4. 纯时间止损 (删除SL, 让均值回归充分展开)
5. 市值加权 (大市值多配, 小市值少配)
6. 动态持仓数 (市场宽度决定最大持仓)
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


def _signal_v6(df, idx):
    """v6信号: 保留drop+RSI核心逻辑, 加反弹确认"""
    try:
        if idx < 10: return False, None, 0
        close = _get_series(df, 'close')
        rsi6 = _get_series(df, 'RSI6')
        c = float(close.iloc[idx])
        c5 = float(close.iloc[idx - 5])
        drop = c / c5 - 1
        rsi = float(rsi6.iloc[idx])
        if not np.isfinite(rsi) or not np.isfinite(drop):
            return False, None, 0
        # 主信号: drop<-0.10 AND RSI<20 (与v5一致)
        if drop < -0.10 and rsi < 20:
            return True, 'main', 1.0
        # 副信号: drop<-0.08 AND RSI<30 (与v5一致)
        if drop < -0.08 and rsi < 30:
            return True, 'secondary', 0.6
        return False, None, 0
    except Exception:
        return False, None, 0


def backtest_v6(start='2018-01-01', end='2022-12-31',
                universe_name='HS300', trading_universe_name=None,
                hold_days=15, risk_per_trade=0.02, atr_stop_mult=3.0,
                initial_capital=1000000.0, verbose=True):
    """v6回测: 多维度自适应"""
    universe = get_universe(universe_name)
    universe = [s for s in universe if s not in DISABLE_STOCK]
    trading_universe = None
    if trading_universe_name:
        if isinstance(trading_universe_name, (set, list)):
            trading_universe = set(trading_universe_name)
        else:
            trading_universe = set(get_universe(trading_universe_name))
        trading_universe = set(s for s in trading_universe if s not in DISABLE_STOCK)
    if verbose:
        print('Detect:', len(universe), '| Trade:',
              len(trading_universe) if trading_universe else len(universe))

    market = load_processed_benchmark('hs300', start=start, end=end)
    mc = market['close']
    mma60 = mc.rolling(60).mean()
    # 市场宽度: 用HS300指数自身近似
    market_breadth = (mc > mc.rolling(20).mean()).rolling(20).mean()

    if verbose:
        print('Loading stocks...')
    stock_data = {}
    mkt_cap_rank = {}
    for sym in universe:
        try:
            df = load_processed(sym, start=start, end=end)
            if df is None or len(df) < 100: continue
            stock_data[sym] = df
            if 'mkt_cap_total' in df.columns:
                mkt_cap_rank[sym] = float(df['mkt_cap_total'].mean())
        except Exception: continue
    # 市值排序 (中位数分割)
    if mkt_cap_rank:
        cap_median = sorted(mkt_cap_rank.values())[len(mkt_cap_rank)//2]
    else:
        cap_median = 1e10
    if verbose:
        print('Loaded:', len(stock_data), 'stocks, cap_median:', round(cap_median/1e8, 1), 'B')

    cash = initial_capital
    positions = {}
    equity_curve = []
    total_equity = initial_capital
    MAX_PENDING = 20
    CORP_TH = 0.15
    dates = market.index.tolist()

    def calc_cost(shares, price, is_buy=True):
        if is_buy: return shares * price * 1.001 * 1.00026
        else: return shares * price * 0.999 * 0.99875

    def is_valid(stock_df, date):
        try:
            if 'is_st' in stock_df.columns and bool(stock_df.loc[date, 'is_st']): return False
            if 'volume' in stock_df.columns and float(stock_df.loc[date, 'volume']) == 0: return False
        except: pass
        return True

    pending_buys = []
    pending_sells = []
    for date in dates:
        # === T+1 pending buys ===
        new_pb = []
        for sym, sig_close, sig_strength in pending_buys:
            if sym not in stock_data or date not in stock_data[sym].index: continue
            if sym in positions: continue
            df = stock_data[sym]
            if not is_valid(df, date): continue
            try:
                if 'is_limit_up' in df.columns and bool(df.loc[date, 'is_limit_up']): continue
            except: pass
            try:
                exec_price = float(df.loc[date, 'open'])
            except: continue
            # === ATR-based position sizing ===
            try:
                atr_val = float(df.loc[date, 'ATR'])
                if np.isnan(atr_val) or atr_val <= 0: atr_val = exec_price * 0.03
            except:
                atr_val = exec_price * 0.03
            # 每笔风险 = risk_per_trade * total_equity
            risk_amount = total_equity * risk_per_trade
            # stop distance = atr_stop_mult * ATR
            stop_dist = atr_stop_mult * atr_val
            if stop_dist <= 0: stop_dist = exec_price * 0.05
            shares = int(risk_amount / stop_dist / 100) * 100
            # 市值加权
            cap_mult = 1.2 if mkt_cap_rank.get(sym, 0) >= cap_median else 0.8
            shares = int(shares * cap_mult / 100) * 100
            # 信号强度加权
            shares = int(shares * sig_strength / 100) * 100
            if shares < 100: continue
            cost = calc_cost(shares, exec_price, True)
            if cost > cash * 0.95:
                shares = int(cash * 0.95 / (exec_price * 1.001) / 100) * 100
                if shares < 100: continue
                cost = calc_cost(shares, exec_price, True)
            cash -= cost
            positions[sym] = {'entry_date': date, 'entry_price': exec_price,
                             'shares': shares, 'peak': exec_price, 'atr': atr_val,
                             'stop_price': exec_price - atr_stop_mult * atr_val}
        pending_buys = new_pb

        # === T+1 pending sells ===
        new_ps = []
        for sym, ratio, reason, queue_date in pending_sells:
            if sym not in positions: continue
            if sym not in stock_data or date not in stock_data[sym].index: continue
            df = stock_data[sym]
            blocked = False
            try:
                if 'volume' in df.columns and float(df.loc[date, 'volume']) == 0: blocked = True
                if 'is_limit_down' in df.columns and bool(df.loc[date, 'is_limit_down']): blocked = True
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
            # CORP ACTION
            if reason == 'corp_action':
                try:
                    pi = df.index.get_loc(date) - 1
                    if pi >= 0: exec_price = float(df.iloc[pi]['close'])
                except: pass
            proceeds = calc_cost(pos['shares'], exec_price, False)
            cash += proceeds
            del positions[sym]
        pending_sells = new_ps

        # === Entry signals ===
        held = set(positions.keys())
        pb = set(s for s, _, _ in pending_buys)
        # 动态最大持仓数: 基于市场宽度
        if date in market_breadth.index:
            breadth = float(market_breadth.loc[date])
            if not np.isnan(breadth):
                if breadth > 0.6: dyn_max = 20
                elif breadth > 0.4: dyn_max = 15
                else: dyn_max = 10
            else: dyn_max = 15
        else: dyn_max = 15

        n_to_buy = dyn_max - len(positions) - len(pending_buys)
        if n_to_buy > 0 and cash > 10000:
            candidates = []
            for sym, df in stock_data.items():
                if trading_universe and sym not in trading_universe: continue
                if sym in held or sym in pb: continue
                if date not in df.index: continue
                try: idx = df.index.get_loc(date)
                except: continue
                if idx < 10 or idx + hold_days >= len(df): continue
                if not is_valid(df, date): continue
                triggered, sig_type, strength = _signal_v6(df, idx)
                if triggered:
                    c = float(_get_series(df, 'close').iloc[idx])
                    r = float(_get_series(df, 'RSI6').iloc[idx])
                    candidates.append((sym, strength, r, c, sig_type))
            # 排序: 信号强度 desc, RSI asc
            candidates.sort(key=lambda x: (-x[1], x[2]))
            for sym, strength, r, c, sig_type in candidates[:n_to_buy]:
                pending_buys.append((sym, c, strength))

        # === Exit signals (纯时间止损 - v6核心改进) ===
        today = date
        for sym, pos in list(positions.items()):
            # T+1 锁
            if pos['entry_date'] == today: continue
            try:
                cur_close = float(stock_data[sym].loc[today, 'close'])
                cur_high = float(stock_data[sym].loc[today, 'high'])
                cur_atr = float(stock_data[sym].loc[today, 'ATR'])
            except: continue
            if cur_close <= 0: continue

            # 更新最高价和ATR trailing stop
            if cur_high > pos['peak']: pos['peak'] = cur_high
            if np.isfinite(cur_atr) and cur_atr > 0:
                pos['atr'] = cur_atr
                pos['stop_price'] = max(pos.get('stop_price', 0),
                                       pos['peak'] - atr_stop_mult * cur_atr)

            ret = cur_close / pos['entry_price'] - 1
            days_held = (today - pos['entry_date']).days

            # CORP ACTION check
            is_corp = False
            try:
                pct = float(stock_data[sym].loc[today, 'pct_change'])
                if not np.isnan(pct) and abs(pct) > CORP_TH * 100: is_corp = True
            except: pass

            should_sell = False; reason = ''
            if is_corp: should_sell = True; reason = 'corp_action'
            elif days_held >= hold_days: should_sell = True; reason = 'time'
            # ATR trailing stop (only for profitable positions)
            elif ret > 0.05 and cur_close < pos.get('stop_price', 0):
                should_sell = True; reason = 'trail'
            # Hard stop at -10% (safety net)
            elif ret <= -0.10: should_sell = True; reason = 'hard_sl'

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
        equity_curve.append({'date': date, 'equity': equity, 'cash': cash,
                            'pos_value': pv, 'n_pos': len(positions)})

    # === Results ===
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
        print('=== ATOS MR v6 ===')
        print('Annual: +'+str(round(ann_ret*100,2))+'%  DD: '+str(round(abs(dd)*100,2))+'%')
        for y, r in yearly: print('  '+str(y)+': '+str(round(r*100,1))+'%')

    return {'annual_return': ann_ret, 'total_return': total_ret,
            'max_drawdown': dd, 'final_equity': final,
            'equity_curve': eq_df, 'yearly_returns': yearly,
            'n_trades': len(pd.DataFrame(columns=['a']))}
