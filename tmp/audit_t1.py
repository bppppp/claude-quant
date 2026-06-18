"""Deep dive on T+1 violations"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.backtest.mr_v2 import backtest_v2

result = backtest_v2('2018-01-01', '2022-12-31', 'HS300', verbose=False)
trades = result['trades']

# Find all T+1 violations
violations = []
for sym, grp in trades.groupby('symbol'):
    b = grp[grp['action'] == 'BUY'].sort_values('date')
    s = grp[grp['action'] == 'SELL'].sort_values('date')
    for _, sell in s.iterrows():
        # Buy on or before sell
        prior = b[b['date'] <= sell['date']]
        if len(prior) == 0:
            continue
        last_buy = prior.iloc[-1]
        if last_buy['date'] == sell['date']:
            violations.append({
                'sym': sym,
                'buy_date': last_buy['date'],
                'sell_date': sell['date'],
                'buy_price': last_buy['price'],
                'sell_price': sell['price'],
                'reason': sell.get('reason', 'unknown'),
            })

print('T+1 violations:', len(violations))
print()
for v in violations[:15]:
    print(f"  {v['sym']} buy={v['buy_date'].date()} @ {v['buy_price']:.2f} -> sell={v['sell_date'].date()} @ {v['sell_price']:.2f} ({v['reason']})")

# Group by reason
print()
print('By reason:')
print(pd.DataFrame(violations)['reason'].value_counts())

# Check: how often is buy_price >= sell_price (would be instant loss)?
print()
for v in violations[:20]:
    pnl = v['sell_price'] / v['buy_price'] - 1
    print(f"  {v['sym']} {v['buy_date'].date()}: buy={v['buy_price']:.2f}, sell={v['sell_price']:.2f}, ret={pnl*100:+.2f}% ({v['reason']})")

# What state was the market in?
print()
print('State distribution of T+1 violation days:')
# Get regime
from atos.data import load_processed_benchmark
from atos.regime import detect_full_regime
market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')
regime_df = detect_full_regime(market, None)
for v in violations:
    if v['buy_date'] in regime_df.index:
        state = regime_df.loc[v['buy_date'], 'effective_state']
        v['state'] = state
    else:
        v['state'] = 'unknown'

print(pd.DataFrame(violations)['state'].value_counts())
