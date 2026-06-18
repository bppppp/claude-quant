import sys; sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
print('Running v6 full analysis...')
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=20,position_pct=0.15,hold_days=10,stop_loss=-0.02,verbose=False)
import numpy as np, pandas as pd
trades=r['trades']; eq=r['equity_curve']; dr=eq['equity'].pct_change().dropna()
paired=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        paired.append({'pnl':s['price']/bl[bi]['price']-1,'days':(s['date']-bl[bi]['date']).days,'reason':s.get('reason','?')})
        bi+=1
pdf=pd.DataFrame(paired); wins=pdf[pdf['pnl']>0]; losses=pdf[pdf['pnl']<=0]
n=len(pdf); wr=len(wins)/n*100
payoff=abs(wins['pnl'].mean()/losses['pnl'].mean())
pf=wins['pnl'].sum()/abs(losses['pnl'].sum())
mw=ml=cw=cl=0
for pn in pdf['pnl']:
    if pn>0: cw+=1; cl=0; mw=max(mw,cw)
    else: cl+=1; cw=0; ml=max(ml,cl)
ann_ret=dr.mean()*252; ann_vol=dr.std()*np.sqrt(252)
sharpe=(ann_ret-0.025)/ann_vol
dn=dr[dr<0]; sortino=(ann_ret-0.025)/(dn.std()*np.sqrt(252)) if len(dn)>0 else 0
calmar=ann_ret/abs(r['max_drawdown'])
skew=pdf['pnl'].skew()
monthly=eq['equity'].resample('ME').last().pct_change().dropna()
mon_wr=(monthly>0).sum()/len(monthly)*100
v5_y={}; prev=1000000
for d,val in eq['equity'].resample('YE').last().items(): v5_y[d.year]=round((val/prev-1)*100,1); prev=val

print('=== ATOS MR v6 DUAL ===')
print('Annual: +%.2f%%'%(r['annual_return']*100))
print('Total:  +%.2f%%'%(r['total_return']*100))
print('MaxDD:  -%.2f%%'%(abs(r['max_drawdown'])*100))
print('Sharpe: %.2f  Sortino: %.2f  Calmar: %.2f'%(sharpe,sortino,calmar))
print('Trades: %d  WR: %.1f%%  Payoff: %.2f  PF: %.2f'%(n,wr,payoff,pf))
print('MaxW/L: %d/%d  Skew: +%.2f  MonWR: %.1f%%'%(mw,ml,skew,mon_wr))
print()
for y in [2018,2019,2020,2021,2022]: print('  %d: %+.1f%%'%(y,v5_y.get(y,0)))
print()
for reason,grp in pdf.groupby('reason'):
    print('  %s: %d WR=%.1f%% avg=%.2f%%'%(reason,len(grp),len(grp[grp['pnl']>0])/len(grp)*100,grp['pnl'].mean()*100))
