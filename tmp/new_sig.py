import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series
codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
codes=[c for c in codes if c not in DISABLE_STOCK]
data={}
for sym in codes[:400]:
 try:
  df=load_processed(sym,start='2018-01-01',end='2022-12-31')
  if df is not None and len(df)>200: data[sym]=df
 except: pass
print('Loaded',len(data),'stocks')

def test_sig(sig_func, hold, label):
 rets=[]; wr=0; total=0
 for sym,df in data.items():
  try:
   close=_get_series(df,'close'); high=_get_series(df,'high'); low=_get_series(df,'low')
   vol=_get_series(df,'volume'); rsi=_get_series(df,'RSI6')
   for d in df.index:
    try:
     idx=df.index.get_loc(d)
     if idx<10 or idx+hold>=len(df): continue
     if sig_func(close,high,low,vol,rsi,idx):
      c=float(close.iloc[idx]); fut=float(close.iloc[idx+hold])
      rets.append(fut/c-1); total+=1
      if fut/c-1>0: wr+=1
    except: continue
  except: continue
 if rets:
  a=np.array(rets)
  print(label+': n='+str(len(a))+' mean='+str(round(a.mean()*100,2))+'% wr='+str(round((a>0).mean()*100,1))+'% med='+str(round(np.median(a)*100,2))+'%')

# Signal 1: Limit-down reversal (跌停次日反弹)
def s1(c,h,l,v,r,idx):
 cur=float(c.iloc[idx]); prev=float(c.iloc[idx-1])
 return cur>prev and cur/prev-1<=-0.095

# Signal 2: Volume exhaustion (连续缩量3日后放量反弹)
def s2(c,h,l,v,r,idx):
 cur=float(c.iloc[idx]); v20=float(v.rolling(20).mean().iloc[idx])
 vcur=float(v.iloc[idx])
 return vcur>v20*1.5 and cur>float(c.iloc[idx-1])

# Signal 3: RSI extreme reversal (RSI<10 then bounce)
def s3(c,h,l,v,r,idx):
 rsi_val=float(r.iloc[idx]); cur=float(c.iloc[idx])
 return rsi_val<10 and cur>float(c.iloc[idx-1])

# Signal 4: Consecutive down 4+ days then bounce
def s4(c,h,l,v,r,idx):
 cur=float(c.iloc[idx])
 dn=sum(1 for i in range(1,5) if idx-i>=0 and float(c.iloc[idx-i])<float(c.iloc[max(0,idx-i-1)]))
 return dn>=4 and cur>float(c.iloc[idx-1])

# Signal 5: Gap down >5% then intraday recovery
def s5(c,h,l,v,r,idx):
 cur=float(c.iloc[idx]); op=float(c.iloc[idx-1])*(1-0.05)
 rng=float(h.iloc[idx])-float(l.iloc[idx])
 if rng<=0: return False
 return (cur-float(l.iloc[idx]))/rng>0.6

print('=== New Signals ===')
for h in [3,5,8,10]: test_sig(s1,h,'1.LimitDownRev hold='+str(h)+'d')
print()
for h in [3,5,8,10]: test_sig(s2,h,'2.VolExhaust hold='+str(h)+'d')
print()
for h in [3,5,8,10]: test_sig(s3,h,'3.RSI_extreme hold='+str(h)+'d')
print()
for h in [3,5,8,10]: test_sig(s4,h,'4.ConsecDown hold='+str(h)+'d')
