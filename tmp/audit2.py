"""Re-audit with correct pct_change threshold"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
from atos.backtest.mr_v2 import backtest_v2
from atos.data import load_processed

result = backtest_v2('2018-01-01', '2022-12-31', 'HS300', verbose=False)
trades = result['trades']

# Check buy day gaps (pct_change in percent, so > 10 is limit)
buys = trades[trades['action'] == 'BUY']
gap_up = 0
gap_dn = 0
extreme = []
for _, t in buys.iterrows():
    df = load_processed(t['symbol'], start=str(t['date'])[:10], end=str(t['date'])[:10])
    if df is None or len(df) == 0:
        continue
    if t['date'] in df.index and 'pct_change' in df.columns:
        pct = float(df.loc[t['date'], 'pct_change'])
        if pct > 10.0:
            gap_up += 1
            extreme.append(('up', t['symbol'], t['date'], pct, t['price']))
        elif pct < -10.0:
            gap_dn += 1
            extreme.append(('down', t['symbol'], t['date'], pct, t['price']))

print('Buy day pct_change > 10%:', gap_up)
print('Buy day pct_change < -10%:', gap_dn)
print('Total extreme days:', len(extreme))
# Check if these are limit up/down
for e in extreme[:20]:
    print(' ', e)

# === Check: are these on limit up/down days? ===
print()
print('=== Checking limit up/down on extreme gap days ===')
limit_violations = []
for typ, sym, date, pct, price in extreme:
    df = load_processed(sym, start=str(date)[:10], end=str(date)[:10])
    if df is None or date not in df.index:
        continue
    if typ == 'up' and 'is_limit_up' in df.columns and bool(df.loc[date, 'is_limit_up']):
        # We bought on a limit-up day - VIOLATION
        limit_violations.append((sym, date, 'limit_up_buy'))
    if typ == 'down' and 'is_limit_down' in df.columns and bool(df.loc[date, 'is_limit_down']):
        # Limit down - we can buy (or not?)
        limit_violations.append((sym, date, 'limit_down_buy'))

print('Limit violations:', len(limit_violations))
for v in limit_violations[:5]:
    print(' ', v)
