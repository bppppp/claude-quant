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

# Collect time exits with D3 tracking
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

# For rally trades (3d up streak + D3>5% + above MA20)
# Trace the profit curve day by day
df_cache={}
daily_profits={idx:[] for idx in range(1,15)}  # day1-day14 profits
rally_count=0
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
        up_streak=d1p>0 and d2p>0 and d3p>0
        above_ma20=d3c>float(ma20.iloc[idx+3]) if not pd.isna(ma20.iloc[idx+3]) else False
        if not (up_streak and d3p>0.05 and above_ma20): continue
        rally_count+=1
        for d in range(1,15):
            if idx+d<len(df):
                daily_profits[d].append(float(close.iloc[idx+d])/ep-1)
    except: continue

print('Rally trades found:',rally_count)
print()
print('=== Day-by-day profit curve (rally trades) ===')
for d in range(1,15):
    if daily_profits[d]:
        arr=np.array(daily_profits[d])
        print('D'+str(d)+': mean='+str(round(arr.mean()*100,2))+'% median='+str(round(np.median(arr)*100,2))+'% max='+str(round(arr.max()*100,1))+'% win='+str(round((arr>0).mean()*100,1))+'%')

# When do they peak?
print()
print('=== Peak timing ===')
peaks=[]
for i in range(rally_count):
    profits=[daily_profits[d][i] for d in range(1,15) if i<len(daily_profits[d])]
    if profits:
        peak_day=np.argmax(profits)+1
        peaks.append((peak_day,max(profits)))
peak_df=pd.DataFrame(peaks,columns=['day','max_profit'])
print('Avg peak day:',round(peak_df['day'].mean(),1))
print('Median peak day:',round(peak_df['day'].median(),1))
print('Peak day distribution:')
for d in range(1,15):
    cnt=(peak_df['day']==d).sum()
    if cnt>0: print('  D'+str(d)+': '+str(cnt)+' trades')
print('Avg max profit:',str(round(peak_df['max_profit'].mean()*100,2))+'%')
