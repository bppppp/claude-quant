"""Test T+1 open return"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.data import load_processed
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]

all_results = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    open_ = _get_series(df, 'open')
    high = _get_series(df, 'high')
    low = _get_series(df, 'low')
    
    big_drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    oversold25 = (rsi6 < 25).fillna(False)
    signal = big_drop & oversold25
    
    df_x = df.copy()
    df_x['rsi6'] = rsi6
    df_x['sig'] = signal
    df_x['open_t1'] = open_.shift(-1)  # T+1 open
    df_x['close_t1'] = close.shift(-1)  # T+1 close
    df_x['close_t3'] = close.shift(-3)  # T+3 close
    df_x['close_t5'] = close.shift(-5)  # T+5 close
    
    # Return from T+1 open to T+3 close
    df_x['ret_t1open_t3close'] = df_x['close_t3'] / df_x['open_t1'] - 1
    df_x['ret_t1open_t5close'] = df_x['close_t5'] / df_x['open_t1'] - 1
    df_x['ret_t0close_t1open'] = df_x['open_t1'] / df_x['close'] - 1  # overnight gap
    
    triggered = df_x[df_x['sig']].copy()
    if len(triggered) > 0:
        triggered['symbol'] = sym
        all_results.append(triggered)

df_all = pd.concat(all_results)
df_all['year'] = df_all.index.year

print('=== T+1 Open Returns (the realistic edge) ===')
print('Overnight gap (T close to T+1 open):')
print('  mean:', round(df_all['ret_t0close_t1open'].mean()*100, 3), '%')
print('  win:', round((df_all['ret_t0close_t1open']>0).mean()*100, 1), '%')

print()
print('T+1 open to T+3 close:')
print('  mean:', round(df_all['ret_t1open_t3close'].mean()*100, 3), '%')
print('  win:', round((df_all['ret_t1open_t3close']>0).mean()*100, 1), '%')

print()
print('T+1 open to T+5 close:')
print('  mean:', round(df_all['ret_t1open_t5close'].mean()*100, 3), '%')
print('  win:', round((df_all['ret_t1open_t5close']>0).mean()*100, 1), '%')

# By year
print()
print('By year (T+1 open to T+5 close):')
for y in [2018, 2019, 2020, 2021, 2022]:
    sub = df_all[df_all['year'] == y]
    if len(sub) > 0:
        print(' ', y, ': n=', len(sub), 'mean=', round(sub['ret_t1open_t5close'].mean()*100, 3), '%', 'win=', round((sub['ret_t1open_t5close']>0).mean()*100, 1), '%')
