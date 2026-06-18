"""Analyze signal firing rates"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.config import StrategyConfig
from atos.data import load_processed
from atos.signals.entry import generate_buy_signals
from data.config import DISABLE_STOCK
from atos.data.universe import get_universe

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]

# Sample 50 stocks
sample = universe[:50]
config = StrategyConfig()

signal_counts = {}
for sym in sample:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    for regime in ['BULL', 'SIDEWAYS', 'BEAR', 'CHOPPY_BEAR']:
        sigs = generate_buy_signals(df, regime, config=config)
        for col in sigs.columns:
            if col.startswith('sig_'):
                count = int(sigs[col].sum())
                key = (col, regime)
                signal_counts[key] = signal_counts.get(key, 0) + count

print('Signal firing rates (per stock per 5 years, averaged):')
for (col, regime), count in sorted(signal_counts.items()):
    avg = count / len(sample)
    print(f'  {regime:<12} {col:<25}: {avg:.1f} days')

# Specifically check sig_mean_reversion
print()
print('sig_mean_reversion per regime:')
for regime in ['BULL', 'SIDEWAYS', 'BEAR', 'CHOPPY_BEAR']:
    key = ('sig_mean_reversion', regime)
    if key in signal_counts:
        print(f'  {regime}: {signal_counts[key] / len(sample):.1f} days')
