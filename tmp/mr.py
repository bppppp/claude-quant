import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed, load_processed_benchmark
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series
all_codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
all_codes=[c for c in all_codes if c not in DISABLE_STOCK]
market=load_processed_benchmark('hs300',start='2018-01-01',end='2022-12-31')
mclose=market['close']; mma20=mclose.rolling(20).mean(); mma60=mclose.rolling(60).mean(); mret=mclose.pct_change()
feats=[]
for sym in all_codes[:300]:
 try:
  df=load_processed(sym,start='2018-01-01',end='2022-12-31')
  if df is None or len(df)<200: continue
  close=_get_series(df,'close'); rsi=_get_series(df,'RSI6')
  for d in df.index:
   try:
    idx=df.index.get_loc(d)
    if idx<30 or idx+10>=len(df): continue
    c=float(close.iloc[idx]); c5=float(close.iloc[idx-5]); r=float(rsi.iloc[idx])
    if not (c/c5-1<-0.08 and r<30): continue
    if d not in mclose.index: continue
    peak10=max([float(close.iloc[idx+d])/c-1 for d in range(1,min(10,len(df)-idx))])
    m_c=float(mclose.loc[d]); m_c5=float(mclose.shift(5).loc[d]) if d in mclose.shift(5).index else m_c
    m_drop=m_c/m_c5-1; m_vol5=mret.rolling(5).std().iloc[mret.index.get_loc(d)]*np.sqrt(252) if d in mret.index else 0.2
    feats.append({'r':peak10>0.15,'peak':peak10,'md':m_drop,'mv':m_vol5})
   except: continue
 except: continue
mf=pd.DataFrame(feats)
print('Signals:',len(mf),'Rally%:',round(mf['r'].mean()*100,1))
for md in [-0.02,-0.03,-0.05,-0.08]:
 sub=mf[mf['md']<=md]
 if len(sub)>30: print('MktDrop<='+str(int(md*100))+'%: n='+str(len(sub))+' rally%='+str(round(sub['r'].mean()*100,1))+'% peak='+str(round(sub['peak'].mean()*100,1))+'%')
sub=mf[(mf['md']<=-0.03)&(mf['mv']>=0.25)]
if len(sub)>30: print('PANIC: n='+str(len(sub))+' rally%='+str(round(sub['r'].mean()*100,1))+'%')
