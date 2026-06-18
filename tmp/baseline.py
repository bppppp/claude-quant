"""Baseline backtest after bug fix"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
import time
from atos.config import StrategyConfig
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from atos.backtest import BacktestEngine
from data.config import DISABLE_STOCK

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]
print('HS300 (filtered):', len(universe))

market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')
print('Market rows:', len(market))

stock_data = {}
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        stock_data[sym] = df
print('Stocks loaded:', len(stock_data))

config = StrategyConfig()
engine = BacktestEngine(config)
t0 = time.time()
result = engine.run(market_df=market, stock_data=stock_data)
print('Backtest time:', round(time.time()-t0, 1), 's')

m = result.metrics
print()
print('=== BASELINE HS300 (after fix) ===')
print('Annual:', round(m.get('annual_return', 0)*100, 2), '%')
print('Total:', round(m.get('total_return', 0)*100, 2), '%')
print('MaxDD:', round(m.get('max_drawdown', 0)*100, 2), '%')
print('Sharpe:', round(m.get('sharpe', 0), 2))
print('Trades:', int(m.get('n_trades', 0)))
print('WinRate:', round(m.get('win_rate', 0)*100, 2), '%')

# Yearly
eq = result.equity_curve
yearly = eq.resample('YE').last().pct_change().dropna()
print()
print('Yearly returns:')
for d, r in yearly.items():
    print('  ', d.year, ':', round(r*100, 2), '%')

# HS300 buy-hold benchmark
print()
print('HS300 buy-hold:')
hs300_buy_hold = market['close'].iloc[0]
for d in [2018, 2019, 2020, 2021, 2022]:
    # find last close of year
    yr_data = market[market.index.year == d]
    if len(yr_data) > 0:
        ret = float(yr_data['close'].iloc[-1]) / float(yr_data['close'].iloc[0]) - 1
        print(f'  {d}: {ret*100:.2f}%')
