import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)

# Monthly rolling: 24-month train, 12-month test, roll by 6 months
results=[]
train_len=24; test_len=12; step=6
for start_m in range(0, 60-test_len-train_len, step):
    train_start=f'2018-{1+start_m%12:02d}-01' if start_m%12==0 else f'2018-{1+start_m%12:02d}-01'
    # simplify: use year-based windows
    pass

# Simpler: test each 12-month period
periods=[
    ('2018-01-01','2018-12-31','2018'),
    ('2019-01-01','2019-12-31','2019'),
    ('2020-01-01','2020-12-31','2020'),
    ('2021-01-01','2021-12-31','2021'),
    ('2022-01-01','2022-12-31','2022'),
    ('2018-01-01','2019-06-30','18H1-19H1'),
    ('2019-07-01','2020-12-31','19H2-20H2'),
    ('2020-01-01','2021-06-30','20H1-21H1'),
    ('2021-07-01','2022-12-31','21H2-22H2'),
]

# Also: 2-year rolling windows
windows_2yr=[
    ('2018-01-01','2019-12-31','18-19'),
    ('2019-01-01','2020-12-31','19-20'),
    ('2020-01-01','2021-12-31','20-21'),
    ('2021-01-01','2022-12-31','21-22'),
]

# 3-year windows
windows_3yr=[
    ('2018-01-01','2020-12-31','18-20'),
    ('2020-01-01','2022-12-31','20-22'),
]

print('=== 单年测试 ===')
for st,en,label in periods:
    r=backtest_v2(st,en,'ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
    a=r['annual_return']*100; d=abs(r['max_drawdown'])*100
    print(f'{label:15s}: ann={a:+6.1f}% dd={d:5.1f}%')

print()
print('=== 2年滚动窗口 ===')
for st,en,label in windows_2yr:
    r=backtest_v2(st,en,'ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
    a=r['annual_return']*100; d=abs(r['max_drawdown'])*100
    print(f'{label:8s}: ann={a:+6.1f}% dd={d:5.1f}%')

print()
print('=== 3年窗口 ===')
for st,en,label in windows_3yr:
    r=backtest_v2(st,en,'ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
    a=r['annual_return']*100; d=abs(r['max_drawdown'])*100
    print(f'{label:8s}: ann={a:+6.1f}% dd={d:5.1f}%')
