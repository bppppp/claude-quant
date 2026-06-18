"""Check trend signal edge in BULL only"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.data import load_processed, load_processed_benchmark
from atos.data.universe import get_universe
from data.config import DISABLE_STOCK
from atos.regime import detect_full_regime
from atos.signals.mean_reversion import _get_series

universe = get_universe('HS300')
universe = [s for s in universe if s not in DISABLE_STOCK]

market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')
regime_df = detect_full_regime(market, None)

# Get daily regime
regime_daily = regime_df['effective_state']

# Test trend pullback signal
trades = []
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is None or len(df) < 100:
        continue
    close = _get_series(df, 'close')
    ma10 = _get_series(df, 'MA10')
    ma60 = _get_series(df, 'MA60')
    
    in_uptrend = (close > ma60).fillna(False)
    near_ma10 = (close > ma10 * 0.95) & (close < ma10 * 1.02)
    near_ma10 = near_ma10.fillna(False)
    signal = in_uptrend & near_ma10
    
    for i in df.index[signal]:
        idx = df.index.get_loc(i)
        if idx + 5 >= len(df):
            continue
        # Find regime on signal date
        sig_date = i
        if sig_date not in regime_daily.index:
            continue
        state = regime_daily.loc[sig_date]
        if state != 'BULL':
            continue
        entry_price = float(df.iloc[idx + 1]['open'])
        exit_price = float(df.iloc[idx + 5]['close'])
        pnl = exit_price / entry_price - 1
        trades.append({'pnl': pnl, 'year': i.year})

tdf = pd.DataFrame(trades)
if len(tdf) > 0:
    print('Trend pullback signal in BULL only:')
    print('  Total:', len(tdf))
    print('  Avg pnl:', round(tdf['pnl'].mean() * 100, 3), '%')
    print('  Win rate:', round((tdf['pnl'] > 0).mean() * 100, 1), '%')
    for y in [2018, 2019, 2020, 2021, 2022]:
        sub = tdf[tdf['year'] == y]
        if len(sub) > 0:
            print(f'  {y}: n={len(sub)}, avg={sub["pnl"].mean()*100:+.3f}%, win={(sub["pnl"]>0).mean()*100:.1f}%')
else:
    print('No trend signals in BULL')
