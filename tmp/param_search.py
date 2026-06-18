"""Quick parameter search to find best config"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
import time
import copy
from atos.config import StrategyConfig
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from atos.backtest import BacktestEngine
from data.config import DISABLE_STOCK

# Load data once
universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]
market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')

stock_data = {}
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        stock_data[sym] = df
print('Loaded', len(stock_data), 'stocks')

# Grid search configs
def make_config(bull_pos, bear_pos, sideways_pos, top_n, hold_bull, hold_bear, single_bull, single_bear):
    c = StrategyConfig()
    c.base_position = {
        'BULL': bull_pos, 'SIDEWAYS': sideways_pos,
        'BEAR': bear_pos, 'CRASH': 0.0, 'CHOPPY_BEAR': bear_pos,
    }
    c.top_n_stocks = {
        'BULL': top_n, 'SIDEWAYS': top_n - 2 if top_n > 2 else 1,
        'BEAR': max(2, top_n - 3), 'CRASH': 0, 'CHOPPY_BEAR': max(2, top_n - 3),
    }
    c.max_holding_days = {
        'BULL': hold_bull, 'SIDEWAYS': 10, 'BEAR': hold_bear, 'CRASH': 1, 'CHOPPY_BEAR': hold_bear,
    }
    c.single_cap_max = {
        'BULL': single_bull, 'SIDEWAYS': single_bull * 0.6,
        'BEAR': single_bear, 'CRASH': 0.0, 'CHOPPY_BEAR': single_bear,
    }
    return c

# Test different configs
configs = [
    # (name, bull_pos, bear_pos, sideways, top_n, hold_bull, hold_bear, single_bull, single_bear)
    ("baseline", 0.95, 0.30, 0.70, 15, 30, 6, 0.20, 0.08),
    ("super_bull", 0.95, 0.20, 0.50, 12, 30, 5, 0.25, 0.05),
    ("aggressive", 0.95, 0.50, 0.80, 20, 20, 8, 0.20, 0.10),
    ("balanced", 0.90, 0.40, 0.70, 15, 20, 6, 0.18, 0.08),
    ("short_term", 0.85, 0.40, 0.70, 15, 10, 3, 0.18, 0.10),
]

results = []
for name, bp, be, sw, tn, hb, hbe, sb, sbe in configs:
    config = make_config(bp, be, sw, tn, hb, hbe, sb, sbe)
    engine = BacktestEngine(config)
    t0 = time.time()
    result = engine.run(market_df=market, stock_data=stock_data)
    elapsed = time.time() - t0
    m = result.metrics
    annual = m.get('annual_return', 0)
    total = m.get('total_return', 0)
    mdd = m.get('max_drawdown', 0)
    n_trades = int(m.get('n_trades', 0))
    wr = m.get('win_rate', 0)
    print(f'{name:<15} ann={annual*100:>+7.2f}% tot={total*100:>+7.2f}% mdd={mdd*100:>+7.2f}% trades={n_trades:>5} wr={wr*100:>5.1f}% t={elapsed:.0f}s')
    results.append((name, annual, mdd, n_trades, wr))

print()
print('Best by annual:')
for r in sorted(results, key=lambda x: -x[1])[:3]:
    print(f'  {r[0]}: {r[1]*100:+.2f}% MDD={r[2]*100:.2f}% trades={r[3]}')
