import numpy as np, pandas as pd
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from atos.data import load_processed_benchmark
from data.config import DISABLE_STOCK
h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
tr=r['trades']; eq=r['equity_curve']; dr=eq['equity'].pct_change().dropna()
market=load_processed_benchmark('hs300',start='2018-01-01',end='2022-12-31')
bm_c=market['close']; bm_d=bm_c.pct_change().dropna()
paired=[]
for sym,grp in tr.groupby('symbol'):
 bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
 sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
 bi=0
 for s in sl:
  while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
  if bi>=len(bl): break
  paired.append({'pnl':s['price']/bl[bi]['price']-1,'reason':s.get('reason','?'),'year':bl[bi]['date'].year})
  bi+=1
pdf=pd.DataFrame(paired); n=len(pdf)
wr=len(pdf[pdf['pnl']>0])/n*100
ann_ret=dr.mean()*252; ann_vol=dr.std()*np.sqrt(252)
sharpe=(ann_ret-0.025)/ann_vol
dn=dr[dr<0]; sortino=(ann_ret-0.025)/(dn.std()*np.sqrt(252)) if len(dn)>0 else 0
calmar=ann_ret/abs(r['max_drawdown'])
monthly=eq['equity'].resample('ME').last().pct_change().dropna()
mon_wr=(monthly>0).sum()/len(monthly)*100
bm_ann=bm_d.mean()*252
v5_y={}; pv=1000000
for d,val in eq['equity'].resample('YE').last().items(): v5_y[d.year]=round((val/pv-1)*100,1); pv=val
print('=== ATOS MR v7 (Breakout) ===')
print('Annual: +'+str(round(r['annual_return']*100,2))+'%  DD: -'+str(round(abs(r['max_drawdown'])*100,2))+'%')
print('Sharpe: '+str(round(sharpe,2))+'  Sortino: '+str(round(sortino,2))+'  Calmar: '+str(round(calmar,2)))
print('Trades: '+str(n)+'  WR: '+str(round(wr,1))+'%  MonWR: '+str(round(mon_wr,1))+'%')
print('Active Prem: +'+str(round((ann_ret-bm_ann)*100,1))+'%')
print()
for y in [2018,2019,2020,2021,2022]: print('  '+str(y)+': '+str(v5_y.get(y,0))+'%')
print()
print('Exit reasons:')
for reason,grp in pdf.groupby('reason'): print('  '+reason+': '+str(len(grp))+' WR='+str(round(len(grp[grp['pnl']>0])/len(grp)*100,1))+'% avg='+str(round(grp['pnl'].mean()*100,2))+'%')
