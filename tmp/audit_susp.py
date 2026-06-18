"""检查 suspended-day sell"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
from atos.backtest.mr_v2 import backtest_v2
from atos.data import load_processed

result = backtest_v2('2018-01-01', '2022-12-31', 'HS300', verbose=False)
trades = result['trades']
sells = trades[trades['action'] == 'SELL']

susp_sells = []
for _, t in sells.iterrows():
    df = load_processed(t['symbol'], start=str(t['date'])[:10], end=str(t['date'])[:10])
    if df is None or len(df) == 0:
        continue
    if t['date'] in df.index and 'volume' in df.columns:
        if float(df.loc[t['date'], 'volume']) == 0:
            susp_sells.append({
                'sym': t['symbol'],
                'date': t['date'],
                'price': t['price'],
                'reason': t.get('reason', 'unknown'),
                'pnl_pct': t.get('pnl_pct', 0),
            })

print('Suspended-day sells:', len(susp_sells))
for s in susp_sells:
    print(' ', s)

# 检查 pct_change > 10% 的 buy 案例 - 是否是除权日
print()
print('=== Checking if pct_change > 10% on buy days is dividend adjustment ===')
buys = trades[trades['action'] == 'BUY']
extreme_buys = []
for _, t in buys.iterrows():
    df = load_processed(t['symbol'], start=str(t['date'])[:10], end=str(t['date'])[:10])
    if df is None or len(df) == 0:
        continue
    if t['date'] in df.index and 'pct_change' in df.columns:
        pct = float(df.loc[t['date'], 'pct_change'])
        if abs(pct) > 0.10:
            extreme_buys.append({
                'sym': t['symbol'],
                'date': t['date'],
                'pct_change': pct,
                'price': t['price'],
            })

print('Buys with > 10% gap day:', len(extreme_buys))
# Sample
for e in extreme_buys[:10]:
    print(' ', e)
