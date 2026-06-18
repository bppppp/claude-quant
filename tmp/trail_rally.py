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

df_cache={}
rally_improve=[]; normal_improve=[]
for _,row in pdf.iterrows():
    sym=row['sym']; ed=row['entry_d']; ep=row['entry_p']
    if sym not in df_cache:
        try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
        except: df_cache[sym]=None
    df=df_cache[sym]
    if df is None: continue
    try:
        idx=df.index.get_loc(ed)
        if idx+10>=len(df): continue
        close=_get_series(df,'close'); ma20=close.rolling(20).mean()
        d1c=float(close.iloc[idx+1]); d2c=float(close.iloc[idx+2]); d3c=float(close.iloc[idx+3])
        d1p=d1c/ep-1; d2p=d2c/ep-1; d3p=d3c/ep-1
        is_rally=(d1p>0 and d2p>0 and d3p>0 and d3p>0.05 and d3c>float(ma20.iloc[idx+3]))
        # Current
        d8_exit=float(close.iloc[idx+8])/ep-1
        # Trail stop at 3%
        peak=0; trail_exit=d8_exit; exit_day=8
        for d in range(5,14):
            if idx+d>=len(df): break
            cur=float(close.iloc[idx+d])/ep-1
            peak=max(peak,cur)
            if cur<peak-0.03: trail_exit=cur; exit_day=d; break
        imp={'d8':d8_exit,'trail':trail_exit,'peak':peak,'better':trail_exit>d8_exit}
        if is_rally: rally_improve.append(imp)
        else: normal_improve.append(imp)
    except: continue

ri=pd.DataFrame(rally_improve); ni=pd.DataFrame(normal_improve)
print('Rally trades:',len(ri),'  Normal trades:',len(ni))
print()
print('=== RALLY ===')
print('D8: '+str(round(ri['d8'].mean()*100,2))+'%  Trail: '+str(round(ri['trail'].mean()*100,2))+'%  Peak: '+str(round(ri['peak'].mean()*100,2))+'%')
print('Trail better in '+str(round(ri['better'].mean()*100,1))+'% of rally trades')
print('Net trail effect: +'+str(round((ri['trail'].mean()-ri['d8'].mean())*100,2))+'%')
print()
print('=== NORMAL ===')
print('D8: '+str(round(ni['d8'].mean()*100,2))+'%  Trail: '+str(round(ni['trail'].mean()*100,2))+'%  Peak: '+str(round(ni['peak'].mean()*100,2))+'%')
print('Trail better in '+str(round(ni['better'].mean()*100,1))+'% of normal trades')
print('Net trail effect: +'+str(round((ni['trail'].mean()-ni['d8'].mean())*100,2))+'%')
