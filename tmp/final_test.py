from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
# Test hd=10,sl=-2% and hd=7,sl=-2%
for hd,sl in [(7,-0.02),(9,-0.02),(10,-0.02),(6,-0.02)]:
 r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=hd,stop_loss=sl,verbose=False)
 print('hd='+str(hd)+' sl=-2%: ann='+str(round(r['annual_return']*100,1))+'% dd='+str(round(abs(r['max_drawdown'])*100,1))+'% tr='+str(r['n_trades']))
