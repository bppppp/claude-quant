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

time_trades=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        if s.get('reason','')=='time':
            time_trades.append({'sym':sym,'pnl':s['price']/bl[bi]['price']-1,'entry_d':bl[bi]['date'],'entry_p':bl[bi]['price']})
        bi+=1
pdf=pd.DataFrame(time_trades)

df_cache={}; results=[]
for _,row in pdf.iterrows():
    sym=row['sym']; ed=row['entry_d']; ep=row['entry_p']
    if sym not in df_cache:
        try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
        except: df_cache[sym]=None
    df=df_cache[sym]
    if df is None: continue
    try:
        idx=df.index.get_loc(ed)
        if idx+14>=len(df): continue
        close=_get_series(df,'close'); ma20=close.rolling(20).mean()
        d1c=float(close.iloc[idx+1]); d2c=float(close.iloc[idx+2]); d3c=float(close.iloc[idx+3])
        d1p=d1c/ep-1; d2p=d2c/ep-1; d3p=d3c/ep-1
        is_rally=(d1p>0 and d2p>0 and d3p>0 and d3p>0.05 and d3c>float(ma20.iloc[idx+3]))
        # Different hold durations
        d8=float(close.iloc[idx+8])/ep-1 if idx+8<len(df) else d3p
        d10=float(close.iloc[idx+10])/ep-1 if idx+10<len(df) else d8
        d12=float(close.iloc[idx+12])/ep-1 if idx+12<len(df) else d8
        d14=float(close.iloc[idx+14])/ep-1 if idx+14<len(df) else d8
        # Peak in D8-D14
        peak=max([float(close.iloc[idx+d])/ep-1 for d in range(8,min(15,len(df)-idx))])
        results.append({'rally':is_rally,'d8':d8,'d10':d10,'d12':d12,'d14':d14,'peak':peak})
    except: continue
rdf=pd.DataFrame(results)
rally=rdf[rdf['rally']]; normal=rdf[~rdf['rally']]
print('Rally:',len(rally),' Normal:',len(normal))
print()
print('=== RALLY: extend hold impact ===')
print('D8 (current): '+str(round(rally['d8'].mean()*100,2))+'%')
print('D10:          '+str(round(rally['d10'].mean()*100,2))+'%')
print('D12:          '+str(round(rally['d12'].mean()*100,2))+'%')
print('D14:          '+str(round(rally['d14'].mean()*100,2))+'%')
print('Peak(D8-D14): '+str(round(rally['peak'].mean()*100,2))+'%')
print()
print('=== NORMAL: extend hold impact ===')
print('D8 (current): '+str(round(normal['d8'].mean()*100,2))+'%')
print('D10:          '+str(round(normal['d10'].mean()*100,2))+'%')
print('D12:          '+str(round(normal['d12'].mean()*100,2))+'%')

# What if: rally → hold to D12, normal → keep D8?
combined_pnl=rally['d12'].sum()+normal['d8'].sum()
current_pnl=rdf['d8'].sum()
print()
print('Current total: '+str(round(current_pnl,2))+'  Rally@D12+Normal@D8: '+str(round(combined_pnl,2)))
print('Improvement: +'+str(round((combined_pnl/current_pnl-1)*100,1))+'%')
