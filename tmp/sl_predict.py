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
mclose=market['close']; mma60=mclose.rolling(60).mean()

# Compare SL vs TIME entries: what's different at entry time?
sl_entries=[]; time_entries=[]
for sym,grp in trades.groupby('symbol'):
    bl=grp[grp['action']=='BUY'].sort_values('date').to_dict('records')
    sl=grp[grp['action']=='SELL'].sort_values('date').to_dict('records')
    bi=0
    for s in sl:
        while bi<len(bl) and bl[bi]['date']>=s['date']: bi+=1
        if bi>=len(bl): break
        entry={'sym':sym,'entry_d':bl[bi]['date'],'entry_p':bl[bi]['price'],'pnl':s['price']/bl[bi]['price']-1}
        if s.get('reason','')=='sl': sl_entries.append(entry)
        elif s.get('reason','')=='time': time_entries.append(entry)
        bi+=1

# Load entry-time features
def get_features(entries, label):
    df_cache={}; feats=[]
    for e in entries:
        sym=e['sym']; d=e['entry_d']; ep=e['entry_p']
        if sym not in df_cache:
            try: df_cache[sym]=load_processed(sym,start='2018-01-01',end='2022-12-31')
            except: df_cache[sym]=None
        df=df_cache[sym]
        if df is None: continue
        try:
            idx=df.index.get_loc(d)
            if idx<5: continue
            close=_get_series(df,'close'); vol=_get_series(df,'volume'); rsi=_get_series(df,'RSI6')
            # Entry features
            drop_5d=float(close.iloc[idx])/float(close.iloc[idx-5])-1
            drop_1d=float(close.iloc[idx])/float(close.iloc[idx-1])-1
            rsi_val=float(rsi.iloc[idx])
            vol_ratio=float(vol.iloc[idx])/float(vol.rolling(20).mean().iloc[idx]) if float(vol.rolling(20).mean().iloc[idx])>0 else 1
            atr_pct=float(_get_series(df,'ATR').iloc[idx])/float(close.iloc[idx]) if float(close.iloc[idx])>0 else 0.03
            # Market state
            mrkt='UNK'
            if d in mma60.index and d in mclose.index:
                m60=float(mma60.loc[d])
                if not np.isnan(m60): mrkt='BULL' if float(mclose.loc[d])>m60 else 'BEAR'
            feats.append({'drop_5d':drop_5d,'drop_1d':drop_1d,'rsi':rsi_val,'vol_ratio':vol_ratio,'atr_pct':atr_pct,'mrkt':mrkt,'pnl':e['pnl'],'label':label})
        except: continue
    return pd.DataFrame(feats)

slf=get_features(sl_entries,'SL'); tmf=get_features(time_entries,'TIME')
print('SL entries:',len(slf),' TIME entries:',len(tmf))
allf=pd.concat([slf,tmf])

print()
print('=== Entry特征: SL vs TIME ===')
for col in ['drop_5d','drop_1d','rsi','vol_ratio','atr_pct']:
    s=round(slf[col].mean(),4); t=round(tmf[col].mean(),4)
    print(col+': SL='+str(s)+' TIME='+str(t)+' diff='+str(round(s-t,4)))

print()
print('=== Market state ===')
print('SL: '+str(slf['mrkt'].value_counts().to_dict()))
print('TIME: '+str(tmf['mrkt'].value_counts().to_dict()))

# Can we filter? Test: remove entries with high drop_5d or high vol_ratio
# SL entries have slightly worse features
best_filter=None; best_score=0
for d5 in np.arange(-0.30,-0.05,0.02):
    keep=allf[allf['drop_5d']>=d5]
    if len(keep)<100: continue
    sl_kept=len(keep[keep['label']=='SL']); tm_kept=len(keep[keep['label']=='TIME'])
    sl_removed=len(slf)-sl_kept; tm_removed=len(tmf)-tm_kept
    # Score: each removed SL saves 1.91% loss, each removed TIME loses 4.69% gain
    score=sl_removed*0.0191-tm_removed*0.0469
    if score>best_score: best_score=score; best_filter=('drop_5d>='+str(round(d5,2)),sl_kept,tm_kept,sl_removed,tm_removed)

print()
print('Best entry filter: '+best_filter[0])
print('  SL kept: '+str(best_filter[1])+' SL removed: '+str(best_filter[2])+' ('+str(round(best_filter[2]/len(slf)*100,1))+'%)')
print('  TIME kept: '+str(best_filter[3])+' TIME removed: '+str(best_filter[4])+' ('+str(round(best_filter[4]/len(tmf)*100,1))+'%)')
print('  Net score: '+str(round(best_score,2)))
