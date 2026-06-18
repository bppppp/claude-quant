import numpy as np, pandas as pd, sys
sys.path.insert(0,'D:/claude-quant')
from atos.data import load_processed
from data.config import DISABLE_STOCK, HS300, CSI1000, CYB_STAR_50
from atos.signals.mean_reversion import _get_series

all_codes=list(set(HS300)|set(CSI1000)|set(CYB_STAR_50))
all_codes=[c for c in all_codes if c not in DISABLE_STOCK]
print('Scanning for rally vs crash signals...')

# For each signal trigger (drop<-10%+RSI<30), check outcome
# Collect entry-time features that predict rally vs crash
features=[]
for sym in all_codes[:500]:
    try:
        df=load_processed(sym,start='2018-01-01',end='2022-12-31')
        if df is None or len(df)<200: continue
        close=_get_series(df,'close'); high=_get_series(df,'high'); low=_get_series(df,'low')
        open_=_get_series(df,'open'); vol=_get_series(df,'volume'); rsi=_get_series(df,'RSI6')
        atr=_get_series(df,'ATR'); ma20=close.rolling(20).mean()
        
        for d in df.index:
            try:
                idx=df.index.get_loc(d)
                if idx<30 or idx+15>=len(df): continue
                c=float(close.iloc[idx]); c5=float(close.iloc[idx-5]); r=float(rsi.iloc[idx])
                if not np.isfinite(r): continue
                if not (c/c5-1<-0.08 and r<30): continue
                
                # OUTCOME: is this a rally or crash?
                peak15=max([float(close.iloc[idx+d])/c-1 for d in range(1,min(15,len(df)-idx))])
                is_rally=peak15>0.15
                
                # === ENTRY-TIME FEATURES ===
                o=float(open_.iloc[idx]); h=float(high.iloc[idx]); l=float(low.iloc[idx])
                v=float(vol.iloc[idx]); v20=float(vol.rolling(20).mean().iloc[idx])
                prev_c=float(close.iloc[idx-1]); ma20v=float(ma20.iloc[idx])
                atr_v=float(atr.iloc[idx])
                
                # 1. Intraday reversal: (close-open)/(high-low) → near 1 = bullish hammer
                intra_range=(h-l); intra_pos=(c-o)/intra_range if intra_range>0 else 0
                
                # 2. Close position within day: (close-low)/(high-low) → near 1 = closed at high
                close_pos=(c-l)/intra_range if intra_range>0 else 0.5
                
                # 3. Volume climax: volume / 20d avg
                vol_climax=v/v20 if v20>0 else 1
                
                # 4. Gap from previous close: (open-prev_close)/prev_close
                overnight_gap=(o-prev_c)/prev_c if prev_c>0 else 0
                
                # 5. Consecutive down days before signal
                cons_down=0; di=idx-1
                while di>0 and float(close.iloc[di])<float(close.iloc[di+1]): cons_down+=1; di-=1
                
                # 6. Distance from MA20
                ma20_dist=c/ma20v-1 if ma20v>0 else 0
                
                # 7. ATR ratio (current vs 20d avg)
                atr_ratio=atr_v/(float(close.iloc[idx-20:idx+1].std())*2) if idx>20 else 1
                
                # 8. RSI slope (RSI today vs RSI 3d ago)
                rsi_slope=r-float(rsi.iloc[idx-3]) if idx>=3 else 0
                
                # 9. Drop depth
                drop_5d=c/c5-1
                
                # 10. Volume trend (vol today vs vol yesterday)
                vol_trend=v/float(vol.iloc[idx-1]) if idx>0 and float(vol.iloc[idx-1])>0 else 1
                
                features.append({
                    'rally':is_rally,'peak':peak15,
                    'intra_pos':intra_pos,'close_pos':close_pos,
                    'vol_climax':vol_climax,'overnight_gap':overnight_gap,
                    'cons_down':cons_down,'ma20_dist':ma20_dist,
                    'atr_ratio':atr_ratio,'rsi_slope':rsi_slope,
                    'drop_5d':drop_5d,'vol_trend':vol_trend,
                    'rsi':r,'sym':sym,'date':d
                })
            except: continue
    except: continue

fdf=pd.DataFrame(features)
print('Total signals:',len(fdf),' Rally:',fdf['rally'].sum())

# Feature comparison
print()
print('=== Rally vs Crash: Feature Means ===')
for col in ['intra_pos','close_pos','vol_climax','overnight_gap','cons_down','ma20_dist','atr_ratio','rsi_slope','drop_5d','vol_trend']:
    r=round(fdf[fdf['rally']][col].mean(),4); c=round(fdf[~fdf['rally']][col].mean(),4)
    diff=r-c; sig='↓↓' if diff<-0.01 else ('↑↑' if diff>0.01 else '--')
    print(col+': rally='+str(r)+' crash='+str(c)+' '+sig)

# Simple rule: combine top discriminators
print()
print('=== Combined signals ===')
# Rule: low overnight_gap (small gap down) + high close_pos (closed near high) + vol_climax>1.5
r1=fdf[(fdf['overnight_gap']>-0.03)&(fdf['close_pos']>0.4)]
r2=fdf[(fdf['overnight_gap']>-0.03)&(fdf['close_pos']>0.4)&(fdf['vol_climax']>1.5)]
r3=fdf[(fdf['close_pos']>0.5)&(fdf['vol_climax']>2.0)]
r4=fdf[(fdf['intra_pos']>0.3)&(fdf['vol_climax']>1.5)]  # intraday reversal + volume
r5=fdf[(fdf['cons_down']>=3)&(fdf['close_pos']>0.4)]  # 3+ down days + closed high

for name,sub in [('gap>-3%+close>0.4',r1),('+vol>1.5',r2),('close>0.5+vol>2',r3),('intra_rev+vol',r4),('3ddn+close>0.4',r5)]:
    if len(sub)>0:
        rr=sub['rally'].mean()*100; total_rr=fdf['rally'].mean()*100
        print(name+': n='+str(len(sub))+' rally%='+str(round(rr,1))+'% vs baseline='+str(round(total_rr,1))+'% lift='+str(round(rr/max(total_rr,0.1),1))+'x')
