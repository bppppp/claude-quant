"""Clean backtest using big_drop+oversold signal"""
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
print('Universe:', len(universe))

market = load_processed_benchmark('hs300', start='2018-01-01', end='2022-12-31')

stock_data = {}
for sym in universe:
    df = load_processed(sym, start='2018-01-01', end='2022-12-31')
    if df is not None and len(df) > 100:
        stock_data[sym] = df

from atos.regime import detect_full_regime
regime_df = detect_full_regime(market, None)
print('Regime counts:', regime_df['effective_state'].value_counts().to_dict())

def compute_signal(df):
    rsi6 = _get_series(df, 'RSI6')
    close = _get_series(df, 'close')
    # F signal: drop<-10% AND RSI<20
    big_drop = (close / close.shift(5) - 1 < -0.10).fillna(False)
    oversold20 = (rsi6 < 20).fillna(False)
    return (big_drop & oversold20).astype(int)


def compute_trend_signal(df):
    """Trend signal: pullback to MA10 in uptrend"""
    close = _get_series(df, 'close')
    ma10 = _get_series(df, 'MA10')
    ma60 = _get_series(df, 'MA60')
    # Pullback: close > MA60 (uptrend) AND close < MA10 * 1.02 AND close > MA10 * 0.95
    in_uptrend = (close > ma60).fillna(False)
    near_ma10 = (close > ma10 * 0.95) & (close < ma10 * 1.02)
    near_ma10 = near_ma10.fillna(False)
    return (in_uptrend & near_ma10).astype(int)

print('Precomputing signals...')
signals = {}
trend_signals = {}
for sym, df in stock_data.items():
    signals[sym] = compute_signal(df)
    trend_signals[sym] = compute_trend_signal(df)

class Config:
    initial_capital = 1000000.0
    commission_rate = 0.00025
    stamp_tax_rate = 0.001
    slippage = 0.001
    transfer_fee = 0.00001
    min_commission = 5.0
    max_positions = 20
    position_pct = 0.15
    hold_days = 10
    take_profit = 0.30
    stop_loss = -0.05
    regime_pos = {'BULL': 1.3, 'SIDEWAYS': 1.0, 'BEAR': 0.40, 'CRASH': 0.0, 'CHOPPY_BEAR': 0.50}

config = Config()
trading_dates = market.index.tolist()
print('Trading days:', len(trading_dates))

cash = config.initial_capital
positions = {}
trades = []
equity_curve = []

def calc_buy_cost(shares, price):
    sp = price * (1 + config.slippage)
    gws = shares * sp
    comm = max(gws * config.commission_rate, config.min_commission)
    tfee = gws * config.transfer_fee
    return gws + comm + tfee

def calc_sell_proceeds(shares, price):
    sp = price * (1 - config.slippage)
    gws = shares * sp
    comm = max(gws * config.commission_rate, config.min_commission)
    stamp = gws * config.stamp_tax_rate
    tfee = gws * config.transfer_fee
    return gws - comm - stamp - tfee

print('Running backtest...')
t0 = time.time()
pending_buys = []
total_equity = config.initial_capital  # Track total equity for sizing
for day_idx, date in enumerate(trading_dates):
    if day_idx % 200 == 0:
        print('  Day', day_idx, '/', len(trading_dates))

    if date in regime_df.index:
        state = regime_df.loc[date, 'effective_state']
    else:
        state = 'SIDEWAYS'

    today_prices = {}
    for sym, df in stock_data.items():
        if date in df.index:
            today_prices[sym] = {
                'open': float(df.loc[date, 'open']),
                'high': float(df.loc[date, 'high']),
                'low': float(df.loc[date, 'low']),
                'close': float(df.loc[date, 'close']),
            }

    # Update total_equity (used for fixed-size positions)
    pos_value_now = 0.0
    for sym, pos in positions.items():
        if sym in today_prices:
            pos_value_now += pos['shares'] * today_prices[sym]['close']
    total_equity = cash + pos_value_now

    # Process pending buys
    if pending_buys:
        new_pending = []
        for sym, sig_date, sig_close in pending_buys:
            if sym not in today_prices:
                new_pending.append((sym, sig_date, sig_close))
                continue
            if sym in positions:
                continue
            exec_price = today_prices[sym]['open']
            try:
                if today_prices[sym]['low'] >= exec_price * 1.095:
                    continue
            except:
                pass
            rsi6 = float(stock_data[sym].loc[sig_date, 'RSI6']) if 'RSI6' in stock_data[sym].columns else 50
            pos_pct = config.position_pct * config.regime_pos.get(state, 0.5)
            per_value = total_equity * pos_pct
            shares = int(per_value / exec_price / 100) * 100
            if shares < 100:
                continue
            cost = calc_buy_cost(shares, exec_price)
            if cost > cash * 0.95:
                affordable = int(cash * 0.95 / (exec_price * (1 + config.commission_rate + config.transfer_fee)) / 100) * 100
                if affordable < 100:
                    continue
                shares = affordable
                cost = calc_buy_cost(shares, exec_price)
            cash -= cost
            positions[sym] = {'entry_date': date, 'entry_price': exec_price, 'shares': shares, 'peak': exec_price, 'sig_rsi6': rsi6}
            trades.append({'date': date, 'symbol': sym, 'action': 'BUY', 'price': exec_price, 'shares': shares, 'rsi6': rsi6})
        pending_buys = new_pending

    # Process exits with default TP
    to_close = []
    cur_tp = config.take_profit
    for sym, pos in list(positions.items()):
        if sym not in today_prices:
            continue
        cur_close = today_prices[sym]['close']
        cur_high = today_prices[sym]['high']
        ret = (cur_close - pos['entry_price']) / pos['entry_price']
        days_held = (date - pos['entry_date']).days
        if cur_high > pos['peak']:
            pos['peak'] = cur_high
        should_sell = False
        reason = ''
        if ret >= cur_tp:
            should_sell = True
            reason = 'tp'
        elif ret <= config.stop_loss:
            should_sell = True
            reason = 'sl'
        elif days_held >= config.hold_days:
            should_sell = True
            reason = 'time'
        elif state == 'CRASH':
            should_sell = True
            reason = 'crash'
        if should_sell:
            exec_price = today_prices[sym]['open']
            proceeds = calc_sell_proceeds(pos['shares'], exec_price)
            cash += proceeds
            trades.append({'date': date, 'symbol': sym, 'action': 'SELL', 'price': exec_price, 'shares': pos['shares'], 'reason': reason, 'pnl_pct': ret})
            to_close.append(sym)
    for sym in to_close:
        del positions[sym]

    if state != 'CRASH':
        n_to_buy = config.max_positions - len(positions) - len(pending_buys)
        if n_to_buy > 0 and cash > 0:
            candidates = []
            for sym, df in stock_data.items():
                if sym in positions or sym in [p[0] for p in pending_buys]:
                    continue
                if date not in df.index:
                    continue
                if signals[sym].get(date, 0) != 1:
                    continue
                if 'is_st' in df.columns:
                    try:
                        if bool(df.loc[date, 'is_st']):
                            continue
                    except:
                        pass
                if 'volume' in df.columns:
                    try:
                        if float(df.loc[date, 'volume']) == 0:
                            continue
                    except:
                        pass
                rsi6 = float(df.loc[date, 'RSI6']) if 'RSI6' in df.columns else 50
                sig_close = float(df.loc[date, 'close'])
                candidates.append((sym, rsi6, sig_close))
            candidates.sort(key=lambda x: x[1])
            for sym, rsi6, sig_close in candidates[:n_to_buy]:
                pending_buys.append((sym, date, sig_close))

    pos_value = 0.0
    for sym, pos in positions.items():
        if sym in today_prices:
            pos_value += pos['shares'] * today_prices[sym]['close']
    equity = cash + pos_value
    equity_curve.append({'date': date, 'equity': equity, 'state': state, 'n_pos': len(positions)})

print('Backtest time:', round(time.time() - t0, 1), 's')

eq_df = pd.DataFrame(equity_curve).set_index('date')
final_equity = eq_df['equity'].iloc[-1]
total_return = final_equity / config.initial_capital - 1
years = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
annual_return = (1 + total_return) ** (1/years) - 1
cummax = eq_df['equity'].cummax()
max_dd = ((eq_df['equity'] - cummax) / cummax).min()

t_df = pd.DataFrame(trades)
sells = t_df[t_df['action'] == 'SELL']
n_round = len(sells)

trades_paired = []
for sym, grp in t_df.groupby('symbol'):
    b = grp[grp['action'] == 'BUY']
    s = grp[grp['action'] == 'SELL']
    for i in range(min(len(b), len(s))):
        trades_paired.append({'pnl_pct': s.iloc[i]['price'] / b.iloc[i]['price'] - 1})
paired_df = pd.DataFrame(trades_paired)
wr = (paired_df['pnl_pct'] > 0).mean() if len(paired_df) > 0 else 0

print()
print('=== CLEAN MR BACKTEST ===')
print('Final equity:', round(final_equity))
print('Total return:', round(total_return * 100, 2), '%')
print('Annual return:', round(annual_return * 100, 2), '%')
print('Max DD:', round(max_dd * 100, 2), '%')
print('Trades:', n_round)
print('Win rate:', round(wr * 100, 1), '%')
if len(paired_df) > 0:
    print('Avg pnl/trade:', round(paired_df['pnl_pct'].mean() * 100, 3), '%')

print()
print('Yearly:')
yearly = eq_df['equity'].resample('YE').last()
yret = yearly.pct_change()
# Also show first year return
prev = config.initial_capital
for d, val in yearly.items():
    r = (val / prev - 1)
    print(' ', d.year, ':', round(r * 100, 2), '%')
    prev = val

print()
print('HS300 benchmark:')
for y in range(2018, 2023):
    yr = market[market.index.year == y]
    if len(yr) > 1:
        ret = float(yr['close'].iloc[-1]) / float(yr['close'].iloc[0]) - 1
        print(' ', y, ':', round(ret * 100, 2), '%')
