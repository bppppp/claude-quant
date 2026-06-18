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
trades=r['trades']

# For EACH trade (both SL and TIME), simulate: if SL was ATR-based instead of fixed -2%
# ATR-based: SL = -max(1.5%, entry_ATR_pct * 0.5)    
# This gives wider SL for high-ATR stocks, minimum -1.5%
df_cache={}; results=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        entry_d=bl[bi]['date']; ep=bl[bi]['price']; actual_reason=s.get('reason','?')
        actual_pnl=s['price']/ep-1
        if sym not in df_cache:
            try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
            except: df_cache[sym]=None
        df=df_cache[sym]
        if df is None: bi+=1; continue
        try:
            idx=df.index.get_loc(entry_d)
            if idx+12>=len(df): bi+=1; continue
            close=_get_series(df,'close'); low=_get_series(df,'low')
            atr_pct=float(_get_series(df,'ATR').iloc[idx])/ep
            if not np.isfinite(atr_pct) or atr_pct<=0: atr_pct=0.03
            # ATR-based SL: wider for high vol
            atr_sl=-max(0.015, atr_pct*0.5)  # min -1.5%, 0.5x ATR
            # Simulate: do we hit the ATR SL before D8?
            hit_atr_sl=False; atr_exit_pnl=0; atr_exit_day=0
            for d in range(1,min(9,len(df)-idx)):
                daily_low=float(low.iloc[idx+d])/ep-1
                if daily_low<=atr_sl:
                    hit_atr_sl=True; atr_exit_pnl=daily_low; atr_exit_day=d; break
            if not hit_atr_sl:
                atr_exit_pnl=float(close.iloc[idx+8])/ep-1 if idx+8<len(df) else actual_pnl
                atr_exit_day=8
            # What about: if NOT hit ATR SL, what's D8 return?
            d8_pnl=float(close.iloc[idx+8])/ep-1 if idx+8<len(df) else actual_pnl
            # Peak in 10d
            peak10=max([float(close.iloc[idx+d])/ep-1 for d in range(1,min(11,len(df)-idx))])
            results.append({'sym':sym,'actual':actual_pnl,'actual_reason':actual_reason,
                           'atr_pct':atr_pct,'atr_sl':atr_sl,'atr_exit':atr_exit_pnl,
                           'hit_atr':hit_atr_sl,'d8':d8_pnl,'peak10':peak10,
                           'atr_better':atr_exit_pnl>actual_pnl})
        except: pass
        bi+=1

rdf=pd.DataFrame(results)
print('Total trades analyzed:',len(rdf))
print()

# Overall comparison
actual_avg=rdf['actual'].mean()*100
atr_avg=rdf['atr_exit'].mean()*100
print('Actual avg PnL: '+str(round(actual_avg,2))+'%')
print('ATR-SL avg PnL: '+str(round(atr_avg,2))+'%')
print('ATR better in: '+str(round(rdf['atr_better'].mean()*100,1))+'%')
print('Net ATR effect: +'+str(round(atr_avg-actual_avg,2))+'%')
print()

# Break down by actual reason
for reason in ['sl','time']:
    sub=rdf[rdf['actual_reason']==reason]
    if len(sub)>0:
        print(reason+': actual='+str(round(sub['actual'].mean()*100,2))+'% atr='+str(round(sub['atr_exit'].mean()*100,2))+'% better='+str(round(sub['atr_better'].mean()*100,1))+'%')

# For SL trades that ATR would save
sl=rdf[rdf['actual_reason']=='sl']
saved=sl[sl['atr_better']]
print()
print('SL saved by ATR: '+str(len(saved))+'/'+str(len(sl))+' ('+str(round(len(saved)/len(sl)*100,1))+'%)')
print('  Actual avg: '+str(round(saved['actual'].mean()*100,2))+'% -> ATR: '+str(round(saved['atr_exit'].mean()*100,2))+'%')
print('  Avg peak10 saved: '+str(round(saved['peak10'].mean()*100,1))+'%')
