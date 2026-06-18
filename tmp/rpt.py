import sys; sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from atos.data import load_processed_benchmark
from data.config import DISABLE_STOCK
import numpy as np, pandas as pd, os, datetime
h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
print('v6: ann='+str(round(r['annual_return']*100,1))+'% dd='+str(round(abs(r['max_drawdown'])*100,1))+'% tr='+str(r['n_trades']))
