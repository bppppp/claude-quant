import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series
codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
codes=[c for c in codes if c not in DISABLE_STOCK]
data={}
for sym in codes[:500]:
 try: df=load_processed(sym,start='2018-01-01',end='2022-12-31')
  if df is not None and len(df)>200: data[sym]=df
 except: pass
print('Loaded',len(data),'stocks')

# Trend dip: buy pullback in uptrend
def sig_trend_dip(c,h,l,v,r,idx):
 if idx<25: return False
 cur=float(c.iloc[idx]); ma20=float(c.rolling(20).mean().iloc[idx])
 ma60=float(c.rolling(60).mean().iloc[idx])
 c5=float(c.iloc[idx-5]); c10=float(c.iloc[idx-10])
 # Uptrend: close>MA60, MA20>MA60 (bull trend)
 if not (cur>ma60 and ma20>ma60): return False
 # Recent pullback: 5d down 3-8%, but above MA60
 drop5=cur/c5-1
 if not (-0.08<drop5<-0.03): return False
 # 10d uptrend (before pullback)
 if not (c10<c5): return False
 return True

# Test forward returns
for h in [5,8,10,15,20]:
 rets=[]; wr=0; total=0
 for sym,df in data.items():
  try:
   c=_get_series(df,'close')
   for d in df.index:
    try:
     idx=df.index.get_loc(d)
     if idx<25 or idx+h>=len(df): continue
     if sig_trend_dip(c,None,None,None,None,idx):
      cur=float(c.iloc[idx]); fut=float(c.iloc[idx+h])
      rets.append(fut/cur-1); total+=1
      if fut/cur-1>0: wr+=1
    except: continue
  except: continue
 if rets:
  a=np.array(rets)
  print('hold='+str(h)+'d: n='+str(len(a))+' mean='+str(round(a.mean()*100,2))+'% wr='+str(round((a>0).mean()*100,1))+'% med='+str(round(np.median(a)*100,2))+'%')

# Compare with v6 MR signal on same stocks
print()
print('=== v6 MR signal (baseline) ===')
for h in [8]:
 rets=[]; wr=0
 for sym,df in data.items():
  try:
   c=_get_series(df,'close'); r=_get_series(df,'RSI6')
   for d in df.index:
    try:
     idx=df.index.get_loc(d)
     if idx<10 or idx+h>=len(df): continue
     cur=float(c.iloc[idx]); c5=float(c.iloc[idx-5])
     rsi_v=float(r.iloc[idx])
     if cur/c5-1<-0.08 and rsi_v<30:
      fut=float(c.iloc[idx+h])
      rets.append(fut/cur-1); wr+=1 if fut/cur-1>0 else 0
    except: continue
  except: continue
 if rets:
  a=np.array(rets)
  print('MR h='+str(h)+'d: n='+str(len(a))+' mean='+str(round(a.mean()*100,2))+'% wr='+str(round((a>0).mean()*100,1))+'%')
print()
# Overlap: how many trend dip signals are ALSO MR signals?
td_set=set(); mr_set=set()
for sym,df in data.items():
 try:
  c=_get_series(df,'close'); r=_get_series(df,'RSI6')
  for d in df.index:
   try:
    idx=df.index.get_loc(d)
    if idx<25: continue
    if sig_trend_dip(c,None,None,None,None,idx): td_set.add((sym,d))
    cur=float(c.iloc[idx]); c5=float(c.iloc[idx-5])
    rsi_v=float(r.iloc[idx])
    if cur/c5-1<-0.08 and rsi_v<30: mr_set.add((sym,d))
   except: continue
 except: continue
overlap=td_set&mr_set
print('Trend dip: '+str(len(td_set))+' MR: '+str(len(mr_set))+' Overlap: '+str(len(overlap))+' ('+str(round(len(overlap)/max(len(td_set),1)*100,1))+'%)')
