"""Diagnose why backtest loses despite edge"""
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
    df_x['open_t1'] = open_.shift(-1)
    df_x['close_t5'] = close.shift(-5)
    df_x['high_t5'] = high.shift(-5).rolling(5).max()  # not quite right
    
    triggered = df_x[df_x['sig']].copy()
    if len(triggered) > 0:
        triggered['symbol'] = sym
        all_results.append(triggered)

df_all = pd.concat(all_results)
df_all['year'] = df_all.index.year

# Look at the "max drawdown" within trade
df_all['ret_t1open_t5close'] = df_all['close_t5'] / df_all['open_t1'] - 1

# Distribution of returns
print('Distribution of T+1 open to T+5 close:')
print(df_all['ret_t1open_t5close'].describe(percentiles=[.05, .1, .25, .5, .75, .9, .95]))

# Loss trades
loss_trades = df_all[df_all['ret_t1open_t5close'] < 0]
print()
print('Loss trade stats:')
print('  count:', len(loss_trades))
print('  mean loss:', loss_trades['ret_t1open_t5close'].mean() * 100, '%')
print('  median loss:', loss_trades['ret_t1open_t5close'].median() * 100, '%')
print('  worst 1%:', loss_trades['ret_t1open_t5close'].quantile(0.01) * 100, '%')

# Win trades
win_trades = df_all[df_all['ret_t1open_t5close'] >= 0]
print()
print('Win trade stats:')
print('  count:', len(win_trades))
print('  mean win:', win_trades['ret_t1open_t5close'].mean() * 100, '%')
print('  median win:', win_trades['ret_t1open_t5close'].median() * 100, '%')

# Net with no costs
gross = df_all['ret_t1open_t5close'].mean()
print()
print('Gross edge (no cost):', round(gross * 100, 3), '% per trade')

# With 0.35% round trip cost
net = gross - 0.0035
print('Net edge (with 0.35% cost):', round(net * 100, 3), '% per trade')

# How many signals fire per day on average?
per_day = df_all.groupby(df_all.index).size()
print()
print('Per day signal count:')
print('  mean:', per_day.mean())
print('  median:', per_day.median())
print('  p90:', per_day.quantile(0.9))
print('  max:', per_day.max())

# Same-day vs T+1 issue
# If we buy same-day open, the stock may have gapped up at open due to the news/drop
print()
print('Same-day open (T) vs T-1 close:')
df_all['ret_t0open'] = df_all['open'] / df_all['close'].shift(1) - 1
print('  mean:', round(df_all['ret_t0open'].mean() * 100, 3), '%')

# T+1 open vs T+1 close
df_all['ret_t1day'] = df_all['close_t5'] / df_all['open_t1'] - 1

# Check if most signals fire when stock is falling (gap down)
# In that case, T's open < T-1's close, and we buy at T's open (high relative to intraday)
