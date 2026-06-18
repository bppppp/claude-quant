import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series

all_codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
all_codes=[c for c in all_codes if c not in DISABLE_STOCK]
print('Testing extreme thresholds...')

# Test: different drop+RSI combos, track rally rate and 10d return
results=[]
for sym in all_codes[:400]:
    try:
        df=load_processed(sym,start='2018-01-01',end='2022-12-31')
        if df is None or len(df)<200: continue
        close=_get_series(df,'close'); rsi=_get_series(df,'RSI6')
        for d in df.index:
            try:
                idx=df.index.get_loc(d)
                if idx<10 or idx+15>=len(df): continue
                c=float(close.iloc[idx]); c5=float(close.iloc[idx-5]); r=float(rsi.iloc[idx])
                if not np.isfinite(r): continue
                drop=c/c5-1
                peak15=max([float(close.iloc[idx+d])/c-1 for d in range(1,min(15,len(df)-idx))])
                f10=float(close.iloc[idx+10])/c-1 if idx+10<len(df) else 0
                f5=float(close.iloc[idx+5])/c-1 if idx+5<len(df) else 0
                results.append({'drop':drop,'rsi':r,'peak15':peak15,'f10':f10,'f5':f5})
            except: continue
    except: continue

rdf=pd.DataFrame(results)
print('Total entries:',len(rdf))
print()

# Test thresholds
thresholds=[
    ('drop<-10% RSI<30',rdf['drop']<-0.10,rdf['rsi']<30),
    ('drop<-15% RSI<20',rdf['drop']<-0.15,rdf['rsi']<20),
    ('drop<-15% RSI<15',rdf['drop']<-0.15,rdf['rsi']<15),
    ('drop<-20% RSI<20',rdf['drop']<-0.20,rdf['rsi']<20),
    ('drop<-20%',rdf['drop']<-0.20,None),
    ('drop<-25%',rdf['drop']<-0.25,None),
    ('drop<-15% RSI<10',rdf['drop']<-0.15,rdf['rsi']<10),
]

for name, d_mask, r_mask in thresholds:
    mask=d_mask
    if r_mask is not None: mask=mask&r_mask
    sub=rdf[mask]
    if len(sub)<50: continue
    rr=sub['peak15']>0.15
    rr20=sub['peak15']>0.20
    print(name+': n='+str(len(sub))+' f5='+str(round(sub['f5'].mean()*100,2))+'% f10='+str(round(sub['f10'].mean()*100,2))+'% rally>15%='+str(round(rr.mean()*100,1))+'% rally>20%='+str(round(rr20.mean()*100,1))+'% peak='+str(round(sub['peak15'].mean()*100,1))+'%')
