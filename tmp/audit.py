"""Audit all trades for A-share compliance and data integrity issues"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.backtest.mr_v2 import backtest_v2

result = backtest_v2('2018-01-01', '2022-12-31', 'HS300', verbose=False)
trades = result['trades']
print('Total trades:', len(trades))
print('Buys:', len(trades[trades['action'] == 'BUY']))
print('Sells:', len(trades[trades['action'] == 'SELL']))
print()

# Pair buys and sells (FIFO per symbol) - each buy matched to NEXT sell
paired = []
for sym, grp in trades.groupby('symbol'):
    b_list = grp[grp['action'] == 'BUY'].sort_values('date').to_dict('records')
    s_list = grp[grp['action'] == 'SELL'].sort_values('date').to_dict('records')
    buy_idx = 0
    for sell in s_list:
        # Find the next buy (FIFO)
        while buy_idx < len(b_list) and b_list[buy_idx]['date'] >= sell['date']:
            buy_idx += 1
        if buy_idx >= len(b_list):
            break
        buy = b_list[buy_idx]
        paired.append({
            'symbol': sym,
            'buy_date': buy['date'],
            'buy_price': buy['price'],
            'sell_date': sell['date'],
            'sell_price': sell['price'],
            'shares': buy['shares'],
            'pnl_pct': sell['price'] / buy['price'] - 1,
            'reason': sell.get('reason', 'unknown'),
        })
        buy_idx += 1
pdf = pd.DataFrame(paired)
print('Paired trades (FIFO):', len(pdf))
print()

# === Check 1: T+1 violations ===
print('=== Check 1: T+1 (buy same day = sell) ===')
t1_viol = 0
for sym, grp in trades.groupby('symbol'):
    b = grp[grp['action'] == 'BUY'].sort_values('date')
    s = grp[grp['action'] == 'SELL'].sort_values('date')
    for _, sell in s.iterrows():
        prior = b[b['date'] <= sell['date']]
        if len(prior) == 0:
            t1_viol += 1
            continue
        last_buy = prior.iloc[-1]
        if last_buy['date'] == sell['date']:
            t1_viol += 1
print('T+1 violations:', t1_viol)

# === Check 2: Limit up/down ===
print()
print('=== Check 2: Limit up/down violations ===')
from atos.data import load_processed
limit_up_buys = 0
limit_down_sells = 0
for _, t in pdf.iterrows():
    df = load_processed(t['symbol'], start=str(t['buy_date'])[:10], end=str(t['sell_date'])[:10])
    if df is None or len(df) == 0:
        continue
    try:
        if t['buy_date'] in df.index and 'is_limit_up' in df.columns:
            if bool(df.loc[t['buy_date'], 'is_limit_up']):
                limit_up_buys += 1
        if t['sell_date'] in df.index and 'is_limit_down' in df.columns:
            if bool(df.loc[t['sell_date'], 'is_limit_down']):
                limit_down_sells += 1
    except Exception:
        pass
print('Buy on limit-up day:', limit_up_buys)
print('Sell on limit-down day:', limit_down_sells)

# === Check 3: Suspended day ===
print()
print('=== Check 3: Trading on suspended (volume=0) days ===')
buy_susp = 0
sell_susp = 0
for _, t in pdf.iterrows():
    df = load_processed(t['symbol'], start=str(t['buy_date'])[:10], end=str(t['sell_date'])[:10])
    if df is None or len(df) == 0:
        continue
    try:
        if t['buy_date'] in df.index and 'volume' in df.columns:
            if float(df.loc[t['buy_date'], 'volume']) == 0:
                buy_susp += 1
        if t['sell_date'] in df.index and 'volume' in df.columns:
            if float(df.loc[t['sell_date'], 'volume']) == 0:
                sell_susp += 1
    except Exception:
        pass
print('Buy on suspended day:', buy_susp)
print('Sell on suspended day:', sell_susp)

# === Check 4: ST ===
print()
print('=== Check 4: ST stock trades ===')
st_count = 0
for _, t in pdf.iterrows():
    df = load_processed(t['symbol'], start=str(t['buy_date'])[:10], end=str(t['sell_date'])[:10])
    if df is None or len(df) == 0:
        continue
    try:
        if t['buy_date'] in df.index and 'is_st' in df.columns:
            if bool(df.loc[t['buy_date'], 'is_st']):
                st_count += 1
    except Exception:
        pass
print('ST trades:', st_count)

# === Check 5: Delisted ===
print()
print('=== Check 5: Delisted stock trades ===')
delist_count = 0
for _, t in pdf.iterrows():
    df = load_processed(t['symbol'], start=str(str(t['buy_date']))[:10], end=str(t['sell_date'])[:10])
    if df is None or len(df) == 0:
        continue
    try:
        if t['buy_date'] in df.index and 'delist_date' in df.columns:
            d = df.loc[t['buy_date'], 'delist_date']
            if d is not None and not isinstance(d, str) and pd.notna(d):
                delist_count += 1
    except Exception:
        pass
print('Delisted trades:', delist_count)

# === Check 6: 100-share lots ===
print()
print('=== Check 6: Non-100 share lots ===')
non_lot = (pdf['shares'] % 100 != 0).sum()
print('Count:', non_lot)

# === Check 7: Extreme overnight gaps ===
print()
print('=== Check 7: Extreme overnight gaps (pct_change) ===')
gap_up = 0
gap_dn = 0
for _, t in pdf.iterrows():
    df = load_processed(t['symbol'], start=str(t['buy_date'])[:10], end=str(t['sell_date'])[:10])
    if df is None or len(df) == 0:
        continue
    try:
        if t['buy_date'] in df.index and 'pct_change' in df.columns:
            pct = float(df.loc[t['buy_date'], 'pct_change'])
            if pct > 0.10:
                gap_up += 1
            elif pct < -0.10:
                gap_dn += 1
    except Exception:
        pass
print('Buy day pct_change > 10%:', gap_up)
print('Buy day pct_change < -10%:', gap_dn)

# === Check 8: Suspicious prices ===
print()
print('=== Check 8: Price sanity ===')
print('Buy < 1 RMB:', (pdf['buy_price'] < 1).sum())
print('Buy > 500 RMB:', (pdf['buy_price'] > 500).sum())
print('Sell < 1 RMB:', (pdf['sell_price'] < 1).sum())
print('Sell > 500 RMB:', (pdf['sell_price'] > 500).sum())

# === Check 9: Hold days ===
print()
print('=== Check 9: Hold day distribution ===')
pdf['hold_days'] = (pdf['sell_date'] - pdf['buy_date']).dt.days
print(pdf['hold_days'].describe())
print('Min hold days:', pdf['hold_days'].min())
print('Max hold days:', pdf['hold_days'].max())

# === Top winners/losers ===
print()
print('=== Top 10 winners ===')
for _, t in pdf.nlargest(10, 'pnl_pct').iterrows():
    print(' ', t['symbol'], t['buy_date'].date(), '->', t['sell_date'].date(),
          'ret=', round(t['pnl_pct']*100, 1), '%', 'reason=', t['reason'])

print()
print('=== Top 10 losers ===')
for _, t in pdf.nsmallest(10, 'pnl_pct').iterrows():
    print(' ', t['symbol'], t['buy_date'].date(), '->', t['sell_date'].date(),
          'ret=', round(t['pnl_pct']*100, 1), '%', 'reason=', t['reason'])

# === Exit reason distribution ===
print()
print('=== Exit reason distribution ===')
print(pdf['reason'].value_counts())

# === PnL by reason ===
print()
print('=== Avg pnl by reason ===')
print(pdf.groupby('reason')['pnl_pct'].agg(['count', 'mean', 'sum']).sort_values('sum', ascending=False))
