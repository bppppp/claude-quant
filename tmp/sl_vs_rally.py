import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from atos.data import load_processed, load_processed_benchmark
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

h=get_universe('HS300'); c=get_universe('CYB_STAR_50')
s352=set(s for s in set(h)|set(c) if s not in DISABLE_STOCK)
r=backtest_v2('2018-01-01','2022-12-31','ALL',trading_universe_name=s352,max_positions=22,position_pct=0.17,hold_days=8,stop_loss=-0.02,verbose=False)
trades=r['trades']; market=load_processed_benchmark('hs300',start='2018-01-01',end='2022-12-31')

# For each SL exit, check: what's the max return in the 15 days after entry?
df_cache={}; sl_analysis=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl_list=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl_list:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        if s.get('reason','')!='sl': bi+=1; continue
        entry_d=bl[bi]['date']; ep=bl[bi]['price']
        if sym not in df_cache:
            try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
            except: df_cache[sym]=None
        df=df_cache[sym]
        if df is None: bi+=1; continue
        try:
            idx=df.index.get_loc(entry_d)
            if idx+15>=len(df): bi+=1; continue
            close=_get_series(df,'close')
            peak15=max([float(close.iloc[idx+d])/ep-1 for d in range(1,min(15,len(df)-idx))])
            # Entry features
            entry_drop=float(close.iloc[idx])/float(close.iloc[idx-5])-1
            entry_rsi=float(_get_series(df,'RSI6').iloc[idx])
            atr_pct=float(_get_series(df,'ATR').iloc[idx])/float(close.iloc[idx])
            # Market
            mrkt='UNK'; mclose=market['close']; mma60=mclose.rolling(60).mean()
            if entry_d in mma60.index and entry_d in mclose.index:
                m60=float(mma60.loc[entry_d])
                if not np.isnan(m60): mrkt='BULL' if float(mclose.loc[entry_d])>m60 else 'BEAR'
            sl_analysis.append({'pnl':s['price']/ep-1,'peak15':peak15,'could_recover':peak15>0.05,
                               'drop':entry_drop,'rsi':entry_rsi,'atr':atr_pct,'mrkt':mrkt,
                               'entry_d':entry_d,'sym':sym})
        except: pass
        bi+=1

sldf=pd.DataFrame(sl_analysis)
print('SL exits:',len(sldf))
recover=sldf[sldf['could_recover']]
print('Would recover >5%:',len(recover),'/'+str(len(sldf)),'('+str(round(len(recover)/len(sldf)*100,1))+'%)')
print()

# What's different about SL exits that would have recovered?
print('=== Recover vs Not: Entry Features ===')
for col in ['drop','rsi','atr']:
    r=round(recover[col].mean(),4); n=round(sldf[~sldf['could_recover']][col].mean(),4)
    print(col+': recover='+str(r)+' not='+str(n))

print()
print('=== Recover vs Not: Market ===')
print('Recover: '+str(recover['mrkt'].value_counts().to_dict()))
print('Not: '+str(sldf[~sldf['could_recover']]['mrkt'].value_counts().to_dict()))

# Can we filter?
for atr_max in [0.03,0.04,0.05,0.06,0.08]:
    keep=sldf[sldf['atr']<=atr_max]
    if len(keep)<10: continue
    kept_rec=len(keep[keep['could_recover']])
    removed_rec=len(recover)-kept_rec
    kept_total=len(keep)
    print('ATR<='+str(round(atr_max*100))+'%: keep='+str(kept_total)+' rec='+str(kept_rec)+' removed_rec='+str(removed_rec))
