import sys; sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r0=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=20,position_pct=0.15,hold_days=10,stop_loss=-0.02,verbose=False)
b0=r0['annual_return']*100; d0=abs(r0['max_drawdown'])*100
print('Baseline: ann=%.1f%% dd=%.1f%%'%(b0,d0))
print()
for hd in [8,9,10,12,14]:
    r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=20,position_pct=0.15,hold_days=hd,stop_loss=-0.02,verbose=False)
    print('hd=%d: ann=%.1f%% dd=%.1f%%'%(hd,r['annual_return']*100,abs(r['max_drawdown'])*100))
print()
for sl in [-0.01,-0.02,-0.03]:
    r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=20,position_pct=0.15,hold_days=10,stop_loss=sl,verbose=False)
    print('sl=%d%%: ann=%.1f%% dd=%.1f%%'%(-int(sl*100),r['annual_return']*100,abs(r['max_drawdown'])*100))
print()
for ps in [0.12,0.15,0.18]:
    r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=20,position_pct=ps,hold_days=10,stop_loss=-0.02,verbose=False)
    print('ps=%.2f: ann=%.1f%% dd=%.1f%%'%(ps,r['annual_return']*100,abs(r['max_drawdown'])*100))
print()
for mp in [15,20,25]:
    r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=mp,position_pct=0.15,hold_days=10,stop_loss=-0.02,verbose=False)
    print('mp=%d: ann=%.1f%% dd=%.1f%%'%(mp,r['annual_return']*100,abs(r['max_drawdown'])*100))
