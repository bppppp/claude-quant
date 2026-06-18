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

# Collect time exits with detailed tracking
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
pdf=pd.DataFrame(time_trades); print('Time exits:',len(pdf))

# Load data and extract early signals
df_cache={}
features=[]
for _,row in pdf.iterrows():
    sym=row['sym']; ed=row['entry_d']; ep=row['entry_p']
    if sym not in df_cache:
        try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
        except: df_cache[sym]=None
    df=df_cache[sym]
    if df is None: continue
    try:
        idx=df.index.get_loc(ed)
        if idx+3>=len(df): continue
        close=_get_series(df,'close'); vol=_get_series(df,'volume'); rsi=_get_series(df,'RSI6')
        high=_get_series(df,'high'); low=_get_series(df,'low'); ma20=close.rolling(20).mean()
        # Day 1-3 prices
        d1c=float(close.iloc[idx+1]); d1h=float(high.iloc[idx+1]); d1l=float(low.iloc[idx+1])
        d2c=float(close.iloc[idx+2]); d3c=float(close.iloc[idx+3]); d3h=float(high.iloc[idx+3])
        d1p=d1c/ep-1; d2p=d2c/ep-1; d3p=d3c/ep-1
        # Entry day stats
        entry_drop=float(close.iloc[idx])/float(close.iloc[idx-5])-1
        entry_rsi=float(rsi.iloc[idx]); entry_vol=float(vol.iloc[idx])
        # Rally signals
        up_streak=1 if d1p>0 else 0; up_streak+=1 if d1p>0 and d2p>0 else 0; up_streak+=1 if d1p>0 and d2p>0 and d3p>0 else 0
        gap_from_ma20=(d3c-float(ma20.iloc[idx+3]))/float(ma20.iloc[idx+3]) if idx+3<len(ma20) and not pd.isna(ma20.iloc[idx+3]) else 0
        vol_ratio=float(vol.iloc[idx+3])/float(vol.iloc[idx+1]) if float(vol.iloc[idx+1])>0 else 1
        intra_range=(d3h-d3c)/(d3h-d1l) if (d3h-d1l)>0 else 0.5
        rsi_change=float(rsi.iloc[idx+3])-entry_rsi
        # Max profit in first 3d
        max3d=max(d1p,d2p,d3p)
        features.append({'pnl':row['pnl'],'d3p':d3p,'up_streak':up_streak,'gap_ma20':gap_from_ma20,'vol_ratio':vol_ratio,'intra_range':intra_range,'rsi_chg':rsi_change,'entry_drop':entry_drop,'entry_rsi':entry_rsi,'max3d':max3d})
    except: continue
fdf=pd.DataFrame(features); print('Samples:',len(fdf))

# Binary: is this a "big winner" (top 20%)?
big_thresh=fdf['pnl'].quantile(0.8)
fdf['big_winner']=fdf['pnl']>=big_thresh
print('Big winner threshold:',round(big_thresh*100,1),'%')
print('Big winners:',fdf['big_winner'].sum(),'/',len(fdf))

# Test individual signals
print()
print('=== Signal power to predict big winners ===')
for col in ['d3p','up_streak','gap_ma20','vol_ratio','intra_range','rsi_chg','max3d']:
    bw=fdf[fdf['big_winner']][col].mean()
    nw=fdf[~fdf['big_winner']][col].mean()
    print(col+': big='+str(round(bw,3))+' normal='+str(round(nw,3))+' ratio='+str(round(bw/max(nw,0.001),1))+'x')

# Combined score: simple rules
# Rule 1: up_streak>=3 (3 straight up days) 
# Rule 2: d3p>5% 
# Rule 3: gap_ma20>0 (above MA20)
r1=fdf[fdf['up_streak']>=3]
r2=fdf[fdf['d3p']>0.05]
r3=fdf[(fdf['up_streak']>=3)&(fdf['d3p']>0.05)]
r4=fdf[(fdf['up_streak']>=3)&(fdf['d3p']>0.05)&(fdf['gap_ma20']>0)]
for name,sub in [('3day up streak',r1),('d3>5%',r2),('streak+d3>5%',r3),('streak+d3>5%+>MA20',r4)]:
    print()
    print(name+': '+str(len(sub))+' trades ('+str(round(len(sub)/len(fdf)*100,1))+'%)')
    print('  avg final='+str(round(sub['pnl'].mean()*100,2))+'% big_wr='+str(round(sub['big_winner'].mean()*100,1))+'%')
    print('  avg max3d='+str(round(sub['max3d'].mean()*100,2))+'%')
