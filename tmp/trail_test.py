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

# For ALL time exits (not just rally), test if trailing stop after D5 improves exit
df_cache={}
improvements=[]
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
        close=_get_series(df,'close'); high=_get_series(df,'high')
        # Current: exit at D8 close
        d8_exit=float(close.iloc[idx+8])/ep-1
        # Trailing stop: after D5, peak starts. If drops 3% from peak, exit
        peak=0
        exit_day=8; trail_exit=d8_exit
        for d in range(5,14):
            if idx+d>=len(df): break
            cur=float(close.iloc[idx+d])/ep-1
            peak=max(peak,cur)
            if cur<peak-0.03:  # dropped 3% from peak
                trail_exit=cur; exit_day=d; break
        improvements.append({'d8':d8_exit,'trail':trail_exit,'peak':peak,'exit_d':exit_day,'better':trail_exit>d8_exit})
    except: continue

imdf=pd.DataFrame(improvements)
print('Time exits analyzed:',len(imdf))
print()
print('Current D8 exit: avg='+str(round(imdf['d8'].mean()*100,2))+'%')
print('Trail exit:      avg='+str(round(imdf['trail'].mean()*100,2))+'%')
print('Peak reached:    avg='+str(round(imdf['peak'].mean()*100,2))+'%')
print('Avg exit day:    '+str(round(imdf['exit_d'].mean(),1)))
print()
print('Trail > D8 in '+str(round(imdf['better'].mean()*100,1))+'% of trades')
print('Avg improvement when better: +'+str(round(imdf[imdf['better']]['trail'].mean()*100-imdf[imdf['better']]['d8'].mean()*100,2))+'%')
print('Avg degradation when worse: '+str(round(imdf[~imdf['better']]['trail'].mean()*100-imdf[~imdf['better']]['d8'].mean()*100,2))+'%')
print()
print('Net effect: +'+str(round((imdf['trail'].mean()-imdf['d8'].mean())*100,2))+'% avg per trade')
