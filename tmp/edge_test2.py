"""Detailed edge analysis - by trigger sub-condition"""
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

# Test with sub-conditions
all_results = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    low = _get_series(df, 'low')
    vol = _get_series(df, 'volume')
    boll_down = _get_series(df, 'BOLL_DOWN')
    
    # Individual conditions
    cond1 = (rsi6 < 25).fillna(False)  # Very oversold
    cond2 = (rsi6 < 35).fillna(False)  # Oversold
    cond3 = (close < boll_down).fillna(False)  # Below BOLL
    cond4 = (close <= low.rolling(20).min() * 1.01).fillna(False)  # 20-day low
    cond5 = (close / close.shift(5) - 1 < -0.08).fillna(False)  # Big drop
    
    df_x = df.copy()
    df_x['rsi6'] = rsi6
    df_x['ret_3d'] = df_x['close'].shift(-3) / df_x['close'] - 1
    df_x['ret_5d'] = df_x['close'].shift(-5) / df_x['close'] - 1
    df_x['ret_10d'] = df_x['close'].shift(-10) / df_x['close'] - 1
    
    for d, r in df_x.iterrows():
        if pd.isna(r['ret_5d']):
            continue
        all_results.append({
            'date': d, 'symbol': sym,
            'rsi6': r['rsi6'],
            'ret_3d': r['ret_3d'], 'ret_5d': r['ret_5d'], 'ret_10d': r['ret_10d'],
            'c1': bool(cond1.loc[d]) if d in cond1.index else False,
            'c2': bool(cond2.loc[d]) if d in cond2.index else False,
            'c3': bool(cond3.loc[d]) if d in cond3.index else False,
            'c4': bool(cond4.loc[d]) if d in cond4.index else False,
            'c5': bool(cond5.loc[d]) if d in cond5.index else False,
        })

adf = pd.DataFrame(all_results)
adf['year'] = pd.to_datetime(adf['date']).dt.year

# Overall
print('Overall 5d return:')
print(f'  mean: {adf["ret_5d"].mean()*100:+.3f}%, win: {(adf["ret_5d"]>0).mean()*100:.1f}%')
print()

# By year  
print('By year (5d):')
print(adf.groupby('year')['ret_5d'].agg(['mean', 'count', lambda x: (x>0).mean()]).rename(columns={'<lambda_0>':'win%'}))

# By individual condition
print()
print('By condition:')
for col in ['c1', 'c2', 'c3', 'c4', 'c5']:
    sub = adf[adf[col]]
    print(f'  {col}: n={len(sub)}, mean={sub["ret_5d"].mean()*100:+.3f}%, win={(sub["ret_5d"]>0).mean()*100:.1f}%')

# Combinations
print()
print('Combinations:')
for name, mask in [
    ('c1 only (RSI<25)', adf['c1'] & ~adf['c2']),
    ('c2 only (25<=RSI<35)', ~adf['c1'] & adf['c2']),
    ('c3 (BOLL) only', adf['c3'] & ~adf['c2']),
    ('c1+c2', adf['c1'] & adf['c2']),
    ('c2+c3', adf['c2'] & adf['c3']),
    ('any 2', (adf['c1'].astype(int) + adf['c2'].astype(int) + adf['c3'].astype(int) + adf['c4'].astype(int) + adf['c5'].astype(int)) >= 2),
    ('any 1+', (adf['c1'].astype(int) + adf['c2'].astype(int) + adf['c3'].astype(int) + adf['c4'].astype(int) + adf['c5'].astype(int)) >= 1),
]:
    sub = adf[mask]
    if len(sub) > 0:
        print(f'  {name}: n={len(sub)}, mean={sub["ret_5d"].mean()*100:+.3f}%, win={(sub["ret_5d"]>0).mean()*100:.1f}%')
