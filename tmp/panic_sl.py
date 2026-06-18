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
mclose=market['close']

# For each trade, check: was market in panic mode at entry?
df_cache={}; results=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        entry_d=bl[bi]['date']; ep=bl[bi]['price']; actual=s['price']/ep-1; reason=s.get('reason','?')
        # Market panic at entry
        m_panic=False; m_drop=0
        if entry_d in mclose.index:
            try:
                m_c=float(mclose.loc[entry_d])
                m_c5=float(mclose.shift(5).loc[entry_d]) if entry_d in mclose.shift(5).index else m_c
                m_drop=m_c/m_c5-1; m_panic=m_drop<-0.05
            except: pass
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
            could_rally=peak15>0.15
            results.append({'reason':reason,'actual':actual,'peak15':peak15,'could_rally':could_rally,'m_panic':m_panic,'m_drop':round(m_drop*100,1)})
        except: pass
        bi+=1

rdf=pd.DataFrame(results)
print('Total trades:',len(rdf))
print()

# SL exits during panic vs normal
sl=rdf[rdf['reason']=='sl']
sl_panic=sl[sl['m_panic']]; sl_normal=sl[~sl['m_panic']]
print('=== SL exits ===')
print('During PANIC (mkt drop>5%): '+str(len(sl_panic))+' trades, rally_rate='+str(round(sl_panic['could_rally'].mean()*100,1))+'% avg_peak='+str(round(sl_panic['peak15'].mean()*100,1))+'%')
print('During NORMAL: '+str(len(sl_normal))+' trades, rally_rate='+str(round(sl_normal['could_rally'].mean()*100,1))+'% avg_peak='+str(round(sl_normal['peak15'].mean()*100,1))+'%')
print()

# Time exits during panic vs normal
tm=rdf[rdf['reason']=='time']
tm_panic=tm[tm['m_panic']]; tm_normal=tm[~tm['m_panic']]
print('=== TIME exits ===')
print('During PANIC: '+str(len(tm_panic))+' trades, avg='+str(round(tm_panic['actual'].mean()*100,2))+'% peak='+str(round(tm_panic['peak15'].mean()*100,1))+'%')
print('During NORMAL: '+str(len(tm_normal))+' trades, avg='+str(round(tm_normal['actual'].mean()*100,2))+'% peak='+str(round(tm_normal['peak15'].mean()*100,1))+'%')
print()

# Panic frequency
panic_days=(sl_panic['m_drop'].apply(lambda x: x<=-5)).sum()
print('Panic signals (mkt drop>5%): '+str(len(sl_panic)+len(tm_panic))+'/'+str(len(rdf))+' ('+str(round((len(sl_panic)+len(tm_panic))/len(rdf)*100,1))+'%)')
print('Recommendation: during panic, relax SL from -2% to -4%')
