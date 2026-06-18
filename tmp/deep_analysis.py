import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from atos.data import load_processed, load_processed_benchmark
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
trades=r['trades']; eq=r['equity_curve']
market=load_processed_benchmark('hs300',start='2018-01-01',end='2022-12-31')

# Pair all trades with market context
paired=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        entry_d=bl[bi]['date']
        # Market context at entry
        mc=None; ma60=None; ma20=None
        if entry_d in market.index:
            mc=float(market.loc[entry_d,'close'])
            ma60=float(market['close'].rolling(60).mean().loc[entry_d]) if entry_d in market['close'].rolling(60).mean().index else None
            ma20=float(market['close'].rolling(20).mean().loc[entry_d]) if entry_d in market['close'].rolling(20).mean().index else None
        regime='UNK'
        if mc and ma60 and not np.isnan(ma60):
            regime='BULL' if mc>ma60 else 'BEAR'
        entry_rsi=None
        try: entry_rsi=float(_get_series(load_processed(sym),'RSI6').loc[entry_d]) if sym in load_processed(sym).index else None
        except: pass
        paired.append({
            'pnl':s['price']/bl[bi]['price']-1,
            'reason':s.get('reason','?'),
            'regime':regime,
            'entry_d':entry_d,
            'entry_p':bl[bi]['price'],
            'sym':sym,
            'year':entry_d.year,
            'month':entry_d.month
        })
        bi+=1
pdf=pd.DataFrame(paired); print('Total trades:',len(pdf))

# Analysis 1: Performance by month/quarter
print()
print('=== 月度胜率 ===')
for m in [1,2,3,4,5,6,7,8,9,10,11,12]:
    sub=pdf[pdf['month']==m]
    if len(sub)>0: print('M'+str(m)+': n='+str(len(sub))+' wr='+str(round(len(sub[sub['pnl']>0])/len(sub)*100,1))+'% avg='+str(round(sub['pnl'].mean()*100,2))+'%')

# Analysis 2: Performance by regime
print()
print('=== 市场状态 ===')
for reg in ['BULL','BEAR']:
    sub=pdf[pdf['regime']==reg]
    if len(sub)>0: print(reg+': n='+str(len(sub))+' wr='+str(round(len(sub[sub['pnl']>0])/len(sub)*100,1))+'% avg='+str(round(sub['pnl'].mean()*100,2))+'%')

# Analysis 3: SL trades - when do they happen most?
print()
print('=== SL退出: 月度分布 ===')
sl_pdf=pdf[pdf['reason']=='sl']
for m in [1,2,3,4,5,6,7,8,9,10,11,12]:
    sub=sl_pdf[sl_pdf['month']==m]
    if len(sub)>0: print('M'+str(m)+': '+str(len(sub))+' SL exits ('+str(round(len(sub)/len(pdf[pdf['month']==m])*100,1))+'% of month)')

# Analysis 4: Time exit quality by regime
print()
print('=== Time退出: 市场状态 ===')
time_pdf=pdf[pdf['reason']=='time']
for reg in ['BULL','BEAR']:
    sub=time_pdf[time_pdf['regime']==reg]
    if len(sub)>0: print(reg+': n='+str(len(sub))+' avg='+str(round(sub['pnl'].mean()*100,2))+'% wr='+str(round(len(sub[sub['pnl']>0])/len(sub)*100,1))+'%')
