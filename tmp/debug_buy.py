"""Debug _execute_buy_on_execution - use real engine instance"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.config import StrategyConfig
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]
market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')
stock_data = {}
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        stock_data[sym] = df
config = StrategyConfig()

from atos.backtest.engine import BacktestEngine
e = BacktestEngine(config)
e.cash = 1_000_000.0
e.positions = {}
e._stock_df_cache = stock_data
e.adaptive = None

print(f'Before: cash={e.cash:.0f}, positions={len(e.positions)}')
e._execute_buy_on_execution('601006', 8.14, 'BEAR', pd.Timestamp('2018-04-04'))
print(f'After 601006: cash={e.cash:.0f}, positions={len(e.positions)}')
if e.positions:
    pos = list(e.positions.values())[0]
    print(f'  pos: symbol={pos.symbol} size={pos.size} entry={pos.entry_price}')

print()
print('=== Test 600309 (volume=0) ===')
e.cash = 1_000_000.0
e.positions = {}
e._execute_buy_on_execution('600309', 36.44, 'BEAR', pd.Timestamp('2018-04-04'))
print(f'After: cash={e.cash:.0f}, positions={len(e.positions)}')

print()
print('=== Test 002027 (volume > 0) ===')
e.cash = 1_000_000.0
e.positions = {}
e._execute_buy_on_execution('002027', 12.04, 'BEAR', pd.Timestamp('2018-04-04'))
print(f'After: cash={e.cash:.0f}, positions={len(e.positions)}')
if e.positions:
    pos = list(e.positions.values())[0]
    print(f'  pos: symbol={pos.symbol} size={pos.size} entry={pos.entry_price}')
