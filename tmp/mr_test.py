"""Test if mean reversion edge exists"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.data import load_processed
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series, signal_mean_reversion_entry

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK][:50]  # sample

# Test the edge
results = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    sig = signal_mean_reversion_entry(df)
    df_x = df.copy()
    df_x['sig'] = sig
    
    # Forward returns for 1, 3, 5, 10 days after signal
    df_x['ret_1d'] = df_x['close'].shift(-1) / df_x['close'] - 1
    df_x['ret_3d'] = df_x['close'].shift(-3) / df_x['close'] - 1
    df_x['ret_5d'] = df_x['close'].shift(-5) / df_x['close'] - 1
    df_x['ret_10d'] = df_x['close'].shift(-10) / df_x['close'] - 1
    
    triggered = df_x[df_x['sig'] == 1]
    if len(triggered) < 10:
        continue
    results.append({
        'symbol': sym,
        'n_signals': len(triggered),
        'avg_1d': triggered['ret_1d'].mean(),
        'avg_3d': triggered['ret_3d'].mean(),
        'avg_5d': triggered['ret_5d'].mean(),
        'avg_10d': triggered['ret_10d'].mean(),
        'win_3d': (triggered['ret_3d'] > 0).mean(),
        'win_5d': (triggered['ret_5d'] > 0).mean(),
    })

rdf = pd.DataFrame(results)
print('Mean reversion edge (per-stock average forward returns):')
print(f'  1d:  avg={rdf["avg_1d"].mean()*100:+.3f}%, win={(rdf["avg_1d"]>0).mean()*100:.1f}%')
print(f'  3d:  avg={rdf["avg_3d"].mean()*100:+.3f}%, win={(rdf["avg_3d"]>0).mean()*100:.1f}%')
print(f'  5d:  avg={rdf["avg_5d"].mean()*100:+.3f}%, win={(rdf["avg_5d"]>0).mean()*100:.1f}%')
print(f'  10d: avg={rdf["avg_10d"].mean()*100:+.3f}%, win={(rdf["avg_10d"]>0).mean()*100:.1f}%')

# By year
print()
print('By year:')
all_results = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    sig = signal_mean_reversion_entry(df)
    df_x = df.copy()
    df_x['sig'] = sig
    df_x['ret_3d'] = df_x['close'].shift(-3) / df_x['close'] - 1
    for d, r in df_x.iterrows():
        if r['sig'] == 1 and not pd.isna(r['ret_3d']):
            all_results.append({'year': d.year, 'ret_3d': r['ret_3d']})

adf = pd.DataFrame(all_results)
print(adf.groupby('year')['ret_3d'].agg(['mean', 'count', lambda x: (x>0).mean()]).rename(columns={'<lambda_0>':'win%'}))

# By RSI level
print()
print('By RSI6 bucket (3d return):')
all_results2 = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    sig = signal_mean_reversion_entry(df)
    rsi6 = _get_series(df, 'RSI6')
    df_x = df.copy()
    df_x['sig'] = sig
    df_x['rsi6'] = rsi6
    df_x['ret_3d'] = df_x['close'].shift(-3) / df_x['close'] - 1
    for d, r in df_x.iterrows():
        if r['sig'] == 1 and not pd.isna(r['ret_3d']):
            all_results2.append({'rsi6': r['rsi6'], 'ret_3d': r['ret_3d']})

adf2 = pd.DataFrame(all_results2)
adf2['bucket'] = pd.cut(adf2['rsi6'], [0, 10, 20, 30, 35, 50, 100])
print(adf2.groupby('bucket', observed=True)['ret_3d'].agg(['mean', 'count']))
