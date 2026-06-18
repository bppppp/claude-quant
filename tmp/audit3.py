"""Final audit - check remaining edge cases"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
from atos.backtest.mr_v2 import backtest_v2
from atos.data import load_processed

result = backtest_v2('2018-01-01', '2022-12-31', 'HS300', verbose=False)
trades = result['trades']

# 1. Check the 1 suspended-day sell
print('=== 1. Suspended-day sells (volume=0) ===')
sells = trades[trades['action'] == 'SELL']
susp = []
for _, t in sells.iterrows():
    df = load_processed(t['symbol'], start=str(t['date'])[:10], end=str(t['date'])[:10])
    if df is None or t['date'] not in df.index:
        continue
    if 'volume' in df.columns and float(df.loc[t['date'], 'volume']) == 0:
        susp.append({
            'sym': t['symbol'], 'date': t['date'], 'price': t['price'],
            'reason': t.get('reason', 'unknown'), 'pnl_pct': t.get('pnl_pct', 0),
        })
print('Count:', len(susp))
for s in susp:
    print(' ', s)
# Check if this is a forced sell (price < open of prev trading day)
if susp:
    s = susp[0]
    df = load_processed(s['sym'], start='2017-01-01', end='2025-12-31')
    # find prev trading day
    prev_dates = df.index[df.index < s['date']]
    if len(prev_dates) > 0:
        prev = prev_dates[-1]
        print(f'  Prev trading day: {prev.date()}, close: {df.loc[prev, "close"]}')
        print(f'  Sell price: {s["price"]} (open * 0.95 = {df.loc[prev, "close"] * 0.95:.2f})')
        print(f'  PnL: {s["pnl_pct"]*100:.2f}%')

# 2. Trades with price > 500
print()
print('=== 2. Trades with buy/sell price > 500 RMB ===')
high_p = trades[(trades['price'] > 500)]
print('Count:', len(high_p))
if len(high_p) > 0:
    print('Sample:')
    for _, t in high_p.head(10).iterrows():
        print(f"  {t['symbol']} {t['date'].date()} action={t['action']} price={t['price']:.2f}")

# 3. Check 002714 (the worst loser)
print()
print('=== 3. Check 002714 (worst loser) ===')
worst = result['trades']
worst_buys = worst[worst['symbol'] == '002714']
print('Trades:')
for _, t in worst_buys.iterrows():
    print(f"  {t['date'].date()} {t['action']} {t['price']:.2f} shares={t['shares']} reason={t.get('reason', '')}")

# 4. Check top 5 losers
print()
print('=== 4. Top 5 losers in detail ===')
paired = []
for sym, grp in trades.groupby('symbol'):
    b_list = grp[grp['action'] == 'BUY'].sort_values('date').to_dict('records')
    s_list = grp[grp['action'] == 'SELL'].sort_values('date').to_dict('records')
    buy_idx = 0
    for sell in s_list:
        while buy_idx < len(b_list) and b_list[buy_idx]['date'] >= sell['date']:
            buy_idx += 1
        if buy_idx >= len(b_list):
            break
        buy = b_list[buy_idx]
        paired.append({
            'sym': sym, 'buy_date': buy['date'], 'buy_price': buy['price'],
            'sell_date': sell['date'], 'sell_price': sell['price'],
            'shares': buy['shares'],
            'pnl_pct': sell['price'] / buy['price'] - 1,
            'reason': sell.get('reason', ''),
        })
        buy_idx += 1
pdf = pd.DataFrame(paired)
top5_l = pdf.nsmallest(5, 'pnl_pct')
for _, t in top5_l.iterrows():
    print(f"  {t['sym']} buy={t['buy_date'].date()} @ {t['buy_price']:.2f} -> sell={t['sell_date'].date()} @ {t['sell_price']:.2f} ret={t['pnl_pct']*100:+.1f}% reason={t['reason']} shares={t['shares']}")
    # Check if limit down on sell day
    df = load_processed(t['sym'], start=str(t['sell_date'])[:10], end=str(t['sell_date'])[:10])
    if df is not None and t['sell_date'] in df.index:
        if 'is_limit_down' in df.columns:
            print(f"    is_limit_down: {df.loc[t['sell_date'], 'is_limit_down']}")
        if 'pct_change' in df.columns:
            print(f"    sell day pct_change: {df.loc[t['sell_date'], 'pct_change']:.2f}%")

# 5. Check first 5 winners
print()
print('=== 5. Top 5 winners in detail ===')
top5_w = pdf.nlargest(5, 'pnl_pct')
for _, t in top5_w.iterrows():
    print(f"  {t['sym']} buy={t['buy_date'].date()} @ {t['buy_price']:.2f} -> sell={t['sell_date'].date()} @ {t['sell_price']:.2f} ret={t['pnl_pct']*100:+.1f}% reason={t['reason']}")

# 6. PnL distribution
print()
print('=== 6. PnL distribution ===')
print('  > +50%:', (pdf['pnl_pct'] > 0.5).sum())
print('  +20% ~ +50%:', ((pdf['pnl_pct'] > 0.2) & (pdf['pnl_pct'] <= 0.5)).sum())
print('  +10% ~ +20%:', ((pdf['pnl_pct'] > 0.1) & (pdf['pnl_pct'] <= 0.2)).sum())
print('  0% ~ +10%:', ((pdf['pnl_pct'] > 0) & (pdf['pnl_pct'] <= 0.1)).sum())
print('  -5% ~ 0%:', ((pdf['pnl_pct'] > -0.05) & (pdf['pnl_pct'] <= 0)).sum())
print('  -10% ~ -5%:', ((pdf['pnl_pct'] > -0.1) & (pdf['pnl_pct'] <= -0.05)).sum())
print('  -20% ~ -10%:', ((pdf['pnl_pct'] > -0.2) & (pdf['pnl_pct'] <= -0.1)).sum())
print('  -50% ~ -20%:', ((pdf['pnl_pct'] > -0.5) & (pdf['pnl_pct'] <= -0.2)).sum())
print('  <= -50%:', (pdf['pnl_pct'] <= -0.5).sum())

# 7. Exit reason stats
print()
print('=== 7. PnL by exit reason ===')
print(pdf.groupby('reason')['pnl_pct'].agg(['count', 'mean', 'sum']).sort_values('sum', ascending=False))
