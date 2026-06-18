"""Simple backtest: take all signals, hold 5 days"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
import time
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
from atos.signals.mean_reversion import _get_series

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]

market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')

stock_data = {}
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        stock_data[sym] = df

# Precompute all signals
all_signals = {}  # (sym, date) -> True
all_data = {}
for sym, df in stock_data.items():
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    big_drop = (close / close.shift(5) - 1 < -0.08).fillna(False)
    oversold25 = (rsi6 < 25).fillna(False)
    signal = big_drop & oversold25
    for d in df.index[signal]:
        all_signals[(sym, d)] = True
    all_data[sym] = df

print('Total signals:', len(all_signals))

# For each signal, compute the actual PnL using T+1 open entry, T+5 close exit
trades = []
for (sym, sig_date), _ in all_signals.items():
    df = all_data[sym]
    try:
        idx = df.index.get_loc(sig_date)
    except:
        continue
    # Entry at T+1 open
    if idx + 1 >= len(df):
        continue
    entry_date = df.index[idx + 1]
    entry_price = float(df.iloc[idx + 1]['open'])
    # Exit at T+5 close (5 trading days later)
    if idx + 5 >= len(df):
        continue
    exit_date = df.index[idx + 5]
    exit_price = float(df.iloc[idx + 5]['close'])
    # Apply costs
    # Buy: 0.025% commission + 0.001% transfer + 0.1% slippage
    # Sell: 0.025% commission + 0.1% stamp + 0.001% transfer + 0.1% slippage
    cost_buy = 0.00025 + 0.00001 + 0.001
    cost_sell = 0.00025 + 0.001 + 0.00001 + 0.001
    pnl = (exit_price * (1 - cost_sell)) / (entry_price * (1 + cost_buy)) - 1
    trades.append({
        'sym': sym, 'sig_date': sig_date, 'entry_date': entry_date,
        'exit_date': exit_date, 'entry_price': entry_price, 'exit_price': exit_price,
        'pnl': pnl, 'year': sig_date.year,
    })

tdf = pd.DataFrame(trades)
print('Trades:', len(tdf))
print('Avg pnl per trade:', round(tdf['pnl'].mean() * 100, 3), '%')
print('Win rate:', round((tdf['pnl'] > 0).mean() * 100, 1), '%')
print('Median pnl:', round(tdf['pnl'].median() * 100, 3), '%')
print('Std pnl:', round(tdf['pnl'].std() * 100, 3), '%')
print()
print('By year:')
for y in [2018, 2019, 2020, 2021, 2022]:
    sub = tdf[tdf['year'] == y]
    if len(sub) > 0:
        print(f'  {y}: n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%, sum={sub["pnl"].sum()*100:+.1f}%')

# Total return
print()
print('Total cumulative pnl (all signals):', round(tdf['pnl'].sum() * 100, 1), '%')
print('Geometric mean (with 1M base, 100k per trade):')
# Each trade is 100k, total capital 1M, can have 10 concurrent
# Sequential: each trade makes 100k * pnl, returns to capital
total = 1_000_000.0
n_concurrent = 10
per_trade = 1_000_000 / n_concurrent
for _, t in tdf.iterrows():
    total += per_trade * t['pnl']
print(f'  Final (sequential, 10 concurrent): {total:,.0f}, return: {(total/1_000_000-1)*100:+.1f}%')
