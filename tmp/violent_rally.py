import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed, load_processed_benchmark
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series

all_codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
all_codes=[c for c in all_codes if c not in DISABLE_STOCK]
print('Scanning ALL 1339 stocks for violent rallies...')

# Find: stocks with 5d drop >8% followed by 10d rally >15%
violent_cases=[]
for sym in all_codes[:400]:
    try:
        df=load_processed(sym,start='2018-01-01',end='2022-12-31')
        if df is None or len(df)<200: continue
        close=_get_series(df,'close'); rsi=_get_series(df,'RSI6')
        for d in df.index:
            try:
                idx=df.index.get_loc(d)
                if idx<10 or idx+15>=len(df): continue
                c=float(close.iloc[idx]); c5=float(close.iloc[idx-5])
                drop=c/c5-1; r=float(rsi.iloc[idx])
                if not np.isfinite(r): continue
                # Trigger condition similar to our signal
                if drop<-0.08 and r<30:
                    # Check forward 10d rally
                    f10=float(close.iloc[idx+10])/c-1
                    f15=float(close.iloc[idx+15])/c-1 if idx+15<len(df) else f10
                    if f10>0.15 or f15>0.20:  # violent rally!
                        violent_cases.append({
                            'sym':sym,'date':d,'drop':round(drop*100,1),'rsi':round(r,1),
                            'price':round(c,2),'f10':round(f10*100,1),'f15':round(f15*100,1),
                            'max':round(max(float(close.iloc[idx+d])/c-1 for d in range(1,min(15,len(df)-idx)))*100,1)
                        })
            except: continue
    except: continue

vdf=pd.DataFrame(violent_cases)
print('Found',len(vdf),'violent rally cases')
if len(vdf)>0:
    print()
    print('Top 10 biggest rallies:')
    top=vdf.nlargest(10,'max')
    for _,row in top.iterrows():
        print('  '+row['sym']+' '+str(row['date'].date())+': drop='+str(row['drop'])+'% RSI='+str(row['rsi'])+' -> max='+str(row['max'])+'% (10d='+str(row['f10'])+'%)')
    print()
    print('Stats: median max='+str(round(vdf['max'].median(),1))+'% mean max='+str(round(vdf['max'].mean(),1))+'%')
    print('By year:')
    vdf['year']=pd.to_datetime(vdf['date']).dt.year
    for y in [2018,2019,2020,2021,2022]:
        sy=vdf[vdf['year']==y]
        if len(sy)>0: print('  '+str(y)+': '+str(len(sy))+' cases, avg max='+str(round(sy['max'].mean(),1))+'%')
