"""Edge by RSI bucket"""
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

trades = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    open_ = _get_series(df, 'open')
    
    big_drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    oversold25 = (rsi6 < 25).fillna(False)
    signal = big_drop & oversold25
    
    for i in df.index[signal]:
        idx = df.index.get_loc(i)
        if idx + 5 >= len(df):
            continue
        entry_price = float(df.iloc[idx + 1]['open'])
        exit_price = float(df.iloc[idx + 5]['close'])
        cost = 0.00025 + 0.00001 + 0.001 + 0.00025 + 0.001 + 0.00001 + 0.001
        pnl = (exit_price * (1 - 0.00025 - 0.001 - 0.00001 - 0.001)) / (entry_price * (1 + 0.00025 + 0.00001 + 0.001)) - 1
        trades.append({
            'rsi6': float(rsi6.loc[i]),
            'drop5d': float((close.loc[i] / close.shift(5).loc[i] - 1)),
            'pnl': pnl,
            'year': i.year,
        })

tdf = pd.DataFrame(trades)
print('Total trades:', len(tdf))
print()
print('Edge by RSI bucket:')
for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25)]:
    sub = tdf[(tdf['rsi6'] >= lo) & (tdf['rsi6'] < hi)]
    if len(sub) > 0:
        print(f'  RSI {lo}-{hi}: n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')

# By drop bucket
print()
print('Edge by drop bucket:')
for lo, hi in [(-0.30, -0.15), (-0.15, -0.12), (-0.12, -0.10), (-0.10, -0.08)]:
    sub = tdf[(tdf['drop5d'] >= lo) & (tdf['drop5d'] < hi)]
    if len(sub) > 0:
        print(f'  Drop {lo*100:.0f}%-{hi*100:.0f}%: n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')

# Best combination
print()
print('Top 50% by drop (most oversold drop):')
median_drop = tdf['drop5d'].median()
sub = tdf[tdf['drop5d'] <= median_drop]
print(f'  n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')
print('Bottom 50% by drop:')
sub = tdf[tdf['drop5d'] > median_drop]
print(f'  n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')

# Try volume filter
print()
print('Top volume filter check:')
all_data = {}
for sym in universe[:50]:  # sample
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        all_data[sym] = df

# Add volume check
vol_results = []
for sym, df in all_data.items():
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    open_ = _get_series(df, 'open')
    vol = _get_series(df, 'volume')
    big_drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    oversold25 = (rsi6 < 25).fillna(False)
    signal = big_drop & oversold25
    vol_ma20 = vol.rolling(20).mean()
    
    for i in df.index[signal]:
        idx = df.index.get_loc(i)
        if idx + 5 >= len(df):
            continue
        entry_price = float(df.iloc[idx + 1]['open'])
        exit_price = float(df.iloc[idx + 5]['close'])
        pnl = exit_price / entry_price - 1
        vol_ratio = float(vol.loc[i] / vol_ma20.loc[i]) if vol_ma20.loc[i] > 0 else 1
        vol_results.append({
            'rsi6': float(rsi6.loc[i]),
            'vol_ratio': vol_ratio,
            'pnl': pnl,
        })

vdf = pd.DataFrame(vol_results)
print('Edge by volume ratio:')
for lo, hi in [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 3.0), (3.0, 100)]:
    sub = vdf[(vdf['vol_ratio'] >= lo) & (vdf['vol_ratio'] < hi)]
    if len(sub) > 0:
        print(f'  Vol ratio {lo}-{hi}: n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')
