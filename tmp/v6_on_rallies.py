import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from atos.data import load_processed
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
trades=r['trades']

# Cross-reference: for each BUY trade, what was the stock's subsequent rally?
df_cache={}; results=[]
for _,buy in trades[trades['action']=='BUY'].iterrows():
    sym=buy['symbol']; d=buy['date']; ep=buy['price']
    if sym not in df_cache:
        try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
        except: df_cache[sym]=None
    df=df_cache[sym]
    if df is None: continue
    try:
        idx=df.index.get_loc(d)
        if idx<5 or idx+15>=len(df): continue
        close=_get_series(df,'close'); rsi=_get_series(df,'RSI6')
        c=float(close.iloc[idx]); c5=float(close.iloc[idx-5])
        drop=c/c5-1; rsi_val=float(rsi.iloc[idx])
        if not np.isfinite(rsi_val): continue
        if drop<-0.08 and rsi_val<30:
            f5=float(close.iloc[idx+5])/c-1
            f8=float(close.iloc[idx+8])/c-1
            f10=float(close.iloc[idx+10])/c-1
            f15=float(close.iloc[idx+15])/c-1
            peak=max([float(close.iloc[idx+d])/c-1 for d in range(1,min(15,len(df)-idx))])
            # What was our actual exit?
            sells=trades[(trades['action']=='SELL')&(trades['symbol']==sym)&(trades['date']>d)]
            actual_exit=None; exit_day=None
            if len(sells)>0:
                actual_exit=sells.iloc[0]['price']/ep-1
                exit_day=(sells.iloc[0]['date']-d).days
            results.append({'sym':sym,'date':d,'drop':drop,'rsi':rsi_val,'peak':peak,'f8':f8,'actual':actual_exit,'exit_d':exit_day})
    except: continue

rdf=pd.DataFrame(results)
print('V6 entries on rally-capable signals:',len(rdf))

# Split: how did v6 perform?
rdf['rally']=rdf['peak']>0.15  # violent = peak >15%
rdf['big_rally']=rdf['peak']>0.30  # huge = peak >30%
rallies=rdf[rdf['rally']]; big=rdf[rdf['big_rally']]

print()
print('=== V6 on VIOLENT RALLIES (>15% peak) ===')
print('Count:',len(rallies),'/'+str(len(rdf))+' ('+str(round(len(rallies)/len(rdf)*100,1))+'%)')
print('Avg peak available: +'+str(round(rallies['peak'].mean()*100,1))+'%')
print('Avg v6 actual exit: +'+str(round(rallies['actual'].mean()*100,1))+'%')
print('Avg exit day: '+str(round(rallies['exit_d'].mean(),1)))
print('Missed gain per trade: +'+str(round((rallies['peak']-rallies['actual']).mean()*100,1))+'%')
print()

print('=== V6 on HUGE RALLIES (>30% peak) ===')
print('Count:',len(big),'/'+str(len(rdf))+' ('+str(round(len(big)/len(rdf)*100,1))+'%)')
print('Avg peak available: +'+str(round(big['peak'].mean()*100,1))+'%')
print('Avg v6 actual exit: +'+str(round(big['actual'].mean()*100,1))+'%')
print('Missed gain per trade: +'+str(round((big['peak']-big['actual']).mean()*100,1))+'%')
print()

# Top 5 missed opportunities
print('=== Top 5 biggest missed rallies ===')
rdf['missed']=rdf['peak']-rdf['actual']
top5=rdf.nlargest(5,'missed')
for _,row in top5.iterrows():
    print('  '+row['sym']+' '+str(row['date'].date())+': peak=+'+str(round(row['peak']*100,1))+'% v6=+'+str(round(row['actual']*100,1))+'% missed=+'+str(round(row['missed']*100,1))+'%')
