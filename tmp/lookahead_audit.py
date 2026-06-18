"""Look-ahead bias audit - check if strategy uses future data"""
import sys
sys.path.insert(0, 'D:/claude-quant')
import pandas as pd
import numpy as np
from atos.backtest.mr_v2 import backtest_v2, _compute_signal_v2, _compute_signal_v2_secondary

print('=' * 60)
print('LOOK-AHEAD BIAS AUDIT')
print('=' * 60)

# === Issue 1: pct_change > 15% corporate action detection ===
# At time T (decision day), we check today_pct_change. This is the pct_change
# from T-1 close to T close. Both are KNOWN at T close. So no look-ahead.
# BUT: the previous_idx = df_sym.index.get_loc(date) - 1 to get "prev trading day"
# This uses df_sym.iloc[prev_idx]['close'] which is the close at index = T-1.
# In a DatetimeIndex, iloc[prev_idx] might not be the calendar T-1 day if there
# are missing dates. Let me verify.
print()
print('=== Issue 1: prev_close index lookup ===')
from atos.data import load_processed
df = load_processed('002714', start='2018-06-25', end='2018-07-10')
date = pd.Timestamp('2018-07-03')
print(f'date = {date.date()}')
print(f'date in index: {date in df.index}')
idx = df.index.get_loc(date)
print(f'iloc[idx] = {df.index[idx].date()}')
print(f'iloc[idx-1] = {df.index[idx-1].date()}')
print(f'iloc[idx-1] close = {df.iloc[idx-1]["close"]}')
print(f'Issue: iloc[idx-1] = previous ROW, not necessarily previous TRADING DAY')
print(f'If dates have gaps, this could be wrong!')

# Check: does the data have any gaps?
gaps = []
for i in range(1, len(df.index)):
    diff = (df.index[i] - df.index[i-1]).days
    if diff > 1:
        gaps.append((df.index[i-1].date(), df.index[i].date(), diff))
if gaps:
    print(f'Date gaps in 002714 data: {gaps[:5]}')
else:
    print('No gaps in this 002714 data')

# === Issue 2: BOLL_DOWN comparison for limit up/down ===
# The check "if today_prices[sym]['low'] >= exec_price * 1.095" uses the same
# day's open, high, low. All known at execution. No look-ahead.
print()
print('=== Issue 2: Limit up/down checks ===')
print('Uses today OHLC - no look-ahead. OK')

# === Issue 3: Secondary signal in BULL ===
# Secondary signal uses 5-day drop and RSI(6). Both are computed at T close.
# No look-ahead. The decision to use it ONLY in BULL is a regime filter.
# But: is the regime known at T? Yes, regime_df is computed from market_df
# which has all market data including T.
print()
print('=== Issue 3: Secondary signal ===')
print('Uses T data only, regime filter uses market data up to T. OK')

# === Issue 4: pending_buys use future prices? ===
# pending_buys are queued at T, executed at T+1 open. The T+1 open is the
# actual open price on T+1. This is T+1 data, but we know we will execute
# at T+1 (we're not using T+1 high to decide to buy). OK.
print()
print('=== Issue 4: pending_buys execution at T+1 open ===')
print('Buy at T+1 open, using T+1 data. The decision to queue was at T close.')
print('This is correct T+1 settlement. OK')

# === Issue 5: MAX_PENDING_DAYS for sell ===
# When sell is pending and limit-down, we re-queue. After MAX_PENDING_DAYS=20
# days, we force sell at 5% discount. The 5% discount is a constant.
# No look-ahead. OK.
print()
print('=== Issue 5: Forced sell after MAX_PENDING_DAYS ===')
print('Forced sell uses 5% discount - constant, no look-ahead. OK')

# === Issue 6: pct_change check for split filter ===
# Before buying, we check if stock had > 15% pct_change in past 5 days.
# This uses past 5 days' data, not future. OK.
print()
print('=== Issue 6: Split filter (15% past 5 days) ===')
print('Uses past 5 days only. OK')

# === Issue 7: total_equity for position sizing ===
# total_equity = cash + position_value_now
# position_value_now uses today's close (mark-to-market).
# This is KNOWN at T close. OK.
print()
print('=== Issue 7: total_equity for position sizing ===')
print('Uses T close for mark-to-market. OK')

# === Issue 8: Regime detection ===
# The regime is detected for the WHOLE period before the backtest loop starts.
# So at T, the regime is KNOWN (using data up to T).
# BUT: is the regime for date T itself known at T close?
# Let me check detect_full_regime to see if it uses future data.
print()
print('=== Issue 8: Regime detection (using future?) ===')
from atos.regime import detect_full_regime
from atos.data import load_processed_benchmark
market = load_processed_benchmark('hs300', start='2018-01-01', end='2018-12-31')
regime_df = detect_full_regime(market, None)
# Check if regime at T uses T+1, T+2, etc.
# Look at the regime detector source
import inspect
print('detect_full_regime source:')
print(inspect.getsource(detect_full_regime)[:2000])
