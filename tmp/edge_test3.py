"""Edge with reversal confirmation"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.data import load_processed
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK][:50]

# Test with reversal: oversold + bounce (today > yesterday)
all_results = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    low = _get_series(df, 'low')
    high = _get_series(df, 'high')
    vol = _get_series(df, 'volume')
    boll_down = _get_series(df, 'BOLL_DOWN')
    
    # Reversal: oversold + today higher than yesterday (bounce starting)
    oversold = (rsi6 < 25).fillna(False)
    bounce = (close > close.shift(1)).fillna(False)
    big_bounce = ((close - low) / (high - low) > 0.5).fillna(False)  # Close in upper half
    big_drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    below_boll = (close < boll_down).fillna(False)
    vol_shrink = (vol < vol.rolling(20).mean() * 0.5).fillna(False)
    
    df_x = df.copy()
    df_x['rsi6'] = rsi6
    df_x['ret_3d'] = df_x['close'].shift(-3) / df_x['close'] - 1
    df_x['ret_5d'] = df_x['close'].shift(-5) / df_x['close'] - 1
    
    # Test multiple conditions
    conds = {
        'oversold_only': oversold,
        'oversold+bounce': oversold & bounce,
        'oversold+big_bounce': oversold & big_bounce,
        'oversold+big_drop': oversold & big_drop,
        'oversold+below_boll': oversold & below_boll,
        'oversold+vol_shrink': oversold & vol_shrink,
        'oversold+below_boll+vol_shrink': oversold & below_boll & vol_shrink,
        'RSI<20': rsi6 < 20,
        'RSI<20+bounce': (rsi6 < 20) & bounce,
        'RSI<15': rsi6 < 15,
        'drop8+oversold': big_drop & oversold,
        'drop5+oversold': ((close/close.shift(5)-1) < -0.05) & oversold,
    }
    
    for name, mask in conds.items():
        for d, r in df_x.iterrows():
            if not mask.loc[d] if d in mask.index else True:
                continue
            if pd.isna(r['ret_5d']):
                continue
            all_results.append({
                'strategy': name, 'date': d, 'symbol': sym,
                'rsi6': r['rsi6'],
                'ret_3d': r['ret_3d'], 'ret_5d': r['ret_5d'],
            })

adf = pd.DataFrame(all_results)
adf['year'] = pd.to_datetime(adf['date']).dt.year

print('Strategy edge (5d, then 3d):')
agg = adf.groupby('strategy').agg(
    n=('ret_5d', 'count'),
    mean_5d=('ret_5d', 'mean'),
    win_5d=('ret_5d', lambda x: (x>0).mean()),
    mean_3d=('ret_3d', 'mean'),
    win_3d=('ret_3d', lambda x: (x>0).mean()),
).sort_values('mean_5d', ascending=False)
for idx, row in agg.iterrows():
    print(f'  {idx:<40} n={int(row["n"]):>5} | 5d: {row["mean_5d"]*100:+.3f}% win={row["win_5d"]*100:.0f}% | 3d: {row["mean_3d"]*100:+.3f}% win={row["win_3d"]*100:.0f}%')

# By year for best
print()
print('Best strategies by year:')
best = ['RSI<20+bounce', 'oversold+big_bounce', 'RSI<20', 'oversold+big_drop', 'oversold+bounce']
for strat in best:
    sub = adf[adf['strategy'] == strat]
    if len(sub) > 0:
        yearly = sub.groupby('year')['ret_5d'].agg(['mean', 'count'])
        print(f'\n  {strat}:')
        for y, r in yearly.iterrows():
            print(f'    {y}: {r["mean"]*100:+.3f}% (n={int(r["count"])})')
