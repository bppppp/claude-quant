"""Test different signal combinations"""
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

# Test different signal combinations
signal_specs = [
    # (name, drop_th, rsi_th, vol_filter)
    ('A: drop<-8%, RSI<25', -0.08, 25, False),
    ('B: drop<-10%, RSI<25', -0.10, 25, False),
    ('C: drop<-12%, RSI<25', -0.12, 25, False),
    ('D: drop<-15%, RSI<20', -0.15, 20, False),
    ('E: drop<-8%, RSI<20, vol<1.5', -0.08, 20, True),
    ('F: drop<-10%, RSI<20', -0.10, 20, False),
    ('G: drop<-12%, RSI<20', -0.12, 20, False),
    ('H: drop<-10%, RSI<15', -0.10, 15, False),
    ('I: drop<-8%, RSI<15', -0.08, 15, False),
]

for name, drop_th, rsi_th, vol_filter in signal_specs:
    trades = []
    for sym, df in stock_data.items():
        rsi6 = _get_series(df, 'RSI6')
        close = _get_series(df, 'close')
        open_ = _get_series(df, 'open')
        vol = _get_series(df, 'volume')
        vol_ma20 = vol.rolling(20).mean()
        
        big_drop = (close / close.shift(5) - 1 < drop_th).fillna(False)
        oversold = (rsi6 < rsi_th).fillna(False)
        if vol_filter:
            vol_ok = (vol < vol_ma20 * 1.5).fillna(False)
            signal = big_drop & oversold & vol_ok
        else:
            signal = big_drop & oversold
        
        for i in df.index[signal]:
            idx = df.index.get_loc(i)
            if idx + 5 >= len(df):
                continue
            entry_price = float(df.iloc[idx + 1]['open'])
            exit_price = float(df.iloc[idx + 5]['close'])
            pnl = (exit_price * (1 - 0.00227)) / (entry_price * (1 + 0.00126)) - 1
            trades.append({'pnl': pnl, 'year': i.year})
    
    tdf = pd.DataFrame(trades)
    if len(tdf) > 0:
        print(f'{name}:')
        print(f'  n={len(tdf):>5}, avg={tdf["pnl"].mean()*100:+.3f}%, win={(tdf["pnl"]>0).mean()*100:.1f}%')
        for y in [2018, 2019, 2020, 2021, 2022]:
            sub = tdf[tdf['year'] == y]
            if len(sub) > 0:
                print(f'    {y}: n={len(sub):>4}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')
        # Simulated return
        per_year = len(tdf) / 5
        print(f'  Signals per year: {per_year:.0f}, per day: {per_year/240:.2f}')
