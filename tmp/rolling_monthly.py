import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)

# Generate all 18-month windows with 3-month step
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

start_date = datetime(2018, 1, 1)
end_date = datetime(2022, 12, 31)
window_months = 18
step_months = 3

windows = []
cur = start_date
while cur + relativedelta(months=window_months) <= end_date:
    w_end = cur + relativedelta(months=window_months)
    windows.append((cur.strftime('%Y-%m-%d'), w_end.strftime('%Y-%m-%d'), cur.strftime('%y%m')+'-'+w_end.strftime('%y%m')))
    cur += relativedelta(months=step_months)

print(f'Total windows: {len(windows)}')
print()

results = []
for st, en, label in windows:
    r = backtest_v2(st, en, 'ALL', trading_universe_name=s352,
                    max_positions=22, position_pct=0.17, hold_days=8, stop_loss=-0.02, verbose=False)
    a = r['annual_return'] * 100
    d = abs(r['max_drawdown']) * 100
    results.append((label, a, d))
    print(f'{label}: ann={a:+6.1f}% dd={d:5.1f}%')

# Statistics
anns = [r[1] for r in results]
dds = [r[2] for r in results]
print()
print(f'=== Rolling Window Stats ({window_months}mo, {step_months}mo step) ===')
print(f'Window count: {len(results)}')
print(f'Annual range: {min(anns):+.1f}% to {max(anns):+.1f}%')
print(f'Annual mean:   {np.mean(anns):+.1f}%')
print(f'Annual median: {np.median(anns):+.1f}%')
print(f'Annual std:    {np.std(anns):.1f}%')
print(f'DD range:      {min(dds):.1f}% to {max(dds):.1f}%')
print(f'All positive:  {all(a > 0 for a in anns)}')
print(f'Ann > 20%:     {sum(1 for a in anns if a > 20)}/{len(anns)} = {sum(1 for a in anns if a > 20)/len(anns)*100:.0f}%')
