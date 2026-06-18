#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ATOS MR v6 Dual — Local Backtest (mirrors JQ/scripts/ATOS_MR_v6_Dual.py)

Purpose: Run the exact same strategy locally so results can be compared
         side-by-side with JoinQuant platform output.

JQ params (matched exactly):
    max_positions=22, position_pct=0.17, hold_days=8
    stop_loss=-0.02, take_profit=0.30
    detection_pool=ALL (HS300+CSI1000+CYB_STAR_50, ~1339 stocks)
    trading_pool=HS300+CYB_STAR_50 (~352 stocks)
    regime_pos_mult: BULL=1.5, SIDEWAYS=1.0, BEAR=0.2, CHOPPY_BEAR=0.3, CRASH=0.0

Usage:
    python scripts/local_v6_dual.py                          # default 2018-2022
    python scripts/local_v6_dual.py --start 2020-01-01       # custom range
    python scripts/local_v6_dual.py --no-trend               # MR-only baseline
    python scripts/local_v6_dual.py --output reports/my_run   # custom output dir

Output (saved to reports/ATOS_MR_v6/local_detailed/):
    equity_curve.csv      — daily equity, state, positions
    trades.csv            — every trade with PnL, reason, regime
    yearly_returns.csv    — annual breakdown
    monthly_returns.csv   — monthly breakdown
    summary.json           — all metrics in machine-readable form
    regime_stats.csv      — per-regime trade count, win rate, cumulative PnL
    sell_reasons.csv      — distribution of exit reasons
    params.txt            — all parameters used
    comparison_guide.md   — how to compare with JQ results
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("local_v6_dual")


# ═══════════════════════════════════════════════════════════════════════
# Parameters — exactly match JQ ATOS_MR_v6_Dual.py
# ═══════════════════════════════════════════════════════════════════════
JQ_PARAMS = {
    "max_positions": 22,
    "position_pct": 0.17,
    "hold_days": 8,
    "stop_loss": -0.02,
    "take_profit": 0.30,
    "max_pending_days": 20,
    "corp_action_th": 15.0,
    "regime_pos_mult": {
        "BULL": 1.5,
        "SIDEWAYS": 1.0,
        "BEAR": 0.2,
        "CHOPPY_BEAR": 0.3,
        "CRASH": 0.0,
    },
    "trend_ma_period": 20,
    "trend_vol_mult": 1.2,
    # Costs (match JQ set_order_cost + FixedSlippage(0.002))
    "commission_rate": 0.00025,   # 0.025%
    "stamp_tax_rate": 0.001,      # 0.1% (sell only)
    "slippage": 0.001,            # 0.1% each side = 0.2% total spread
    "transfer_fee": 0.00001,      # 0.001%
    "min_commission": 5.0,
    "initial_capital": 1_000_000.0,
    # State detection
    "regime_lag_days": 3,         # T-3 lag to avoid look-ahead
}


def _safe_col(df, col):
    """Extract column safely (handles duplicate-column DataFrames)."""
    val = df[col]
    if isinstance(val, pd.DataFrame):
        return val.iloc[:, 0]
    return val


def compute_mr_signal(df, idx):
    """Signal A: Mean Reversion (matches JQ compute_signals_jq).

    Main:  5d drop < -10% AND RSI(6) < 20
    Secondary: 5d drop < -8% AND RSI(6) < 30 (BULL only, handled upstream)
    """
    try:
        if idx < 10:
            return False, "none", float("nan")
        close = _safe_col(df, "close")
        rsi6 = _safe_col(df, "RSI6")
        c = float(close.iloc[idx])
        c5 = float(close.iloc[idx - 5])
        drop = c / c5 - 1
        rsi = float(rsi6.iloc[idx])
        if not np.isfinite(rsi) or not np.isfinite(drop):
            return False, "none", float("nan")
        if drop < -0.10 and rsi < 20:
            return True, "main", rsi
        if drop < -0.08 and rsi < 30:
            return True, "secondary", rsi
        return False, "none", float("nan")
    except Exception:
        return False, "none", float("nan")


def compute_trend_signal(df, idx, vol_mult=1.2, ma_period=20):
    """Signal B: Trend Following (matches JQ compute_trend_signals_jq).

    MA20 breakthrough: today close > MA20 AND yesterday close < MA20
    Volume confirmation: volume > vol_mult * 20d avg volume
    """
    try:
        if idx < ma_period + 1:
            return False
        close = _safe_col(df, "close")
        vol = _safe_col(df, "volume")
        c = float(close.iloc[idx])
        c1 = float(close.iloc[idx - 1])
        ma20 = float(close.rolling(ma_period).mean().iloc[idx])
        v = float(vol.iloc[idx])
        v20 = float(vol.rolling(ma_period).mean().iloc[idx])
        if not all(np.isfinite([c, c1, ma20, v, v20])):
            return False
        if v20 <= 0:
            return False
        return c > ma20 and c1 < ma20 and v > vol_mult * v20
    except Exception:
        return False


def check_corp_action(df, idx, threshold=15.0):
    """Detect corporate action (single day pct_change > threshold%)."""
    try:
        if "pct_change" in df.columns:
            pct = float(_safe_col(df, "pct_change").iloc[idx])
            if np.isfinite(pct) and abs(pct) > threshold:
                return True
    except Exception:
        pass
    return False


def check_recent_extreme(df, idx, threshold=15.0, lookback=5):
    """Check if stock had extreme moves (>threshold%) in recent days."""
    try:
        if "pct_change" not in df.columns:
            return True  # can't check, allow
        start = max(0, idx - lookback)
        recent = _safe_col(df, "pct_change").iloc[start:idx + 1]
        if any(abs(float(x)) > threshold for x in recent if np.isfinite(float(x))):
            return False
    except Exception:
        pass
    return True


def calc_buy_cost(shares, price, p):
    """Calculate buy cost including slippage, commission, transfer fee."""
    sp = price * (1 + p["slippage"])
    gross = shares * sp
    comm = max(gross * p["commission_rate"], p["min_commission"])
    tfee = gross * p["transfer_fee"]
    return gross + comm + tfee


def calc_sell_proceeds(shares, price, p):
    """Calculate sell proceeds after slippage, commission, stamp tax, transfer fee."""
    sp = price * (1 - p["slippage"])
    gross = shares * sp
    comm = max(gross * p["commission_rate"], p["min_commission"])
    stamp = gross * p["stamp_tax_rate"]
    tfee = gross * p["transfer_fee"]
    return gross - comm - stamp - tfee


def load_universe(detection_pool="ALL"):
    """Load stock universe matching JQ pools."""
    from data.config import HS300, CSI1000, CYB_STAR_50, DISABLE_STOCK

    pools = {
        "HS300": HS300,
        "CSI1000": CSI1000,
        "CYB_STAR_50": CYB_STAR_50,
        "ALL": sorted(set(HS300 + CSI1000 + CYB_STAR_50)),
        "HS300_CYB50": sorted(set(HS300 + CYB_STAR_50)),
    }
    codes = pools.get(detection_pool, pools["ALL"])
    return [c for c in codes if c not in DISABLE_STOCK]


def load_stock_data(universe, start, end, verbose=True):
    """Load all stock data and pre-compute signals."""
    from atos.data import load_processed

    stock_data = {}
    mr_signals = {}       # {sym: Series of (triggered, sig_type, rsi)}
    mr_secondary = {}     # {sym: Series of (triggered, sig_type, rsi)} — BULL only
    trend_signals = {}    # {sym: Series of bool}

    total = len(universe)
    for i, sym in enumerate(universe):
        if verbose and i % 200 == 0:
            logger.info(f"  Loading {i}/{total}...")
        try:
            df = load_processed(sym, start=start, end=end)
            if df is None or len(df) < 100:
                continue
            if not isinstance(df.index, pd.DatetimeIndex):
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")

            # Pre-compute all signals for the full series
            mr_main_list = []
            mr_sec_list = []
            trend_list = []
            for idx in range(len(df)):
                trig, stype, rsi = compute_mr_signal(df, idx)
                mr_main_list.append(1 if (trig and stype == "main") else 0)
                # secondary: triggered AND type is secondary
                mr_sec_list.append(1 if (trig and stype == "secondary") else 0)
                trend_list.append(1 if compute_trend_signal(df, idx) else 0)

            stock_data[sym] = df
            mr_signals[sym] = pd.Series(mr_main_list, index=df.index, dtype=int)
            mr_secondary[sym] = pd.Series(mr_sec_list, index=df.index, dtype=int)
            trend_signals[sym] = pd.Series(trend_list, index=df.index, dtype=int)
        except Exception as e:
            logger.debug(f"  Skip {sym}: {e}")
            continue

    if verbose:
        logger.info(f"  Loaded {len(stock_data)} stocks")
    return stock_data, mr_signals, mr_secondary, trend_signals


def detect_regime_lagged(market_df, lag_days=3):
    """Detect regime with T-N lag to avoid look-ahead bias.

    Matches JQ detect_regime_jq which uses idx=-4 (T-3).
    """
    from atos.regime import detect_full_regime

    # Compute regime normally on full market data
    raw = detect_full_regime(market_df, None)

    # Lag: shift effective_state by N business days
    lagged = raw.copy()
    lagged["effective_state"] = raw["effective_state"].shift(lag_days, freq="B")
    lagged["effective_state"] = lagged["effective_state"].fillna("SIDEWAYS")
    return lagged


def run_backtest(
    start="2018-01-01",
    end="2022-12-31",
    detection_pool="ALL",
    trading_pool="HS300_CYB50",
    params=None,
    enable_trend=True,
    verbose=True,
):
    """Run complete backtest mirroring JQ ATOS_MR_v6_Dual.

    Returns:
        dict with equity_curve, trades_df, metrics, yearly, monthly,
             regime_stats, sell_reasons
    """
    p = params or JQ_PARAMS
    t0 = time.time()

    # ── 1. Load market data ──────────────────────────────────────────
    from atos.data import load_processed_benchmark
    logger.info("=== Step 1: Load market benchmark ===")
    market = load_processed_benchmark("hs300", start=start, end=end)
    if market is None or len(market) == 0:
        raise ValueError("No market data loaded")

    # ── 2. Load universes ────────────────────────────────────────────
    logger.info(f"=== Step 2: Load universes ===")
    detection_codes = load_universe(detection_pool)
    logger.info(f"  Detection pool ({detection_pool}): {len(detection_codes)} codes")

    if trading_pool == "HS300_CYB50":
        from data.config import HS300, CYB_STAR_50, DISABLE_STOCK
        trading_set = set(c for c in (HS300 + CYB_STAR_50) if c not in DISABLE_STOCK)
    elif trading_pool == "SAME":
        trading_set = None  # no restriction
    else:
        trading_codes = load_universe(trading_pool)
        trading_set = set(trading_codes)
    if trading_set:
        logger.info(f"  Trading pool ({trading_pool}): {len(trading_set)} codes")

    # ── 3. Load stock data + signals ─────────────────────────────────
    logger.info("=== Step 3: Load stock data & pre-compute signals ===")
    stock_data, mr_signals, mr_secondary, trend_signals = load_stock_data(
        detection_codes, start, end, verbose=verbose
    )

    # ── 4. Regime detection (lagged) ─────────────────────────────────
    logger.info("=== Step 4: Detect market regime (lagged) ===")
    regime_df = detect_regime_lagged(market, p["regime_lag_days"])
    if verbose:
        counts = regime_df["effective_state"].value_counts().to_dict()
        logger.info(f"  Regime distribution: {counts}")

    # ── 5. Main backtest loop ────────────────────────────────────────
    logger.info("=== Step 5: Running backtest loop ===")
    trading_dates = market.index.tolist()

    cash = p["initial_capital"]
    positions = {}    # sym -> {entry_date, entry_price, shares, peak, last_close}
    pending_buys = []  # [(sym, sig_date)]
    pending_sells = [] # [(sym, ratio, reason, queue_date)]
    trades = []
    equity_curve = []
    total_equity = p["initial_capital"]

    for day_idx, date in enumerate(trading_dates):
        # ── State lookup ──
        try:
            state = regime_df.loc[date, "effective_state"]
        except KeyError:
            state = "SIDEWAYS"

        # ── Gather today's prices ──
        today_prices = {}
        for sym, df in stock_data.items():
            if date in df.index:
                try:
                    today_prices[sym] = {
                        "open": float(_safe_col(df, "open").loc[date]),
                        "high": float(_safe_col(df, "high").loc[date]),
                        "low": float(_safe_col(df, "low").loc[date]),
                        "close": float(_safe_col(df, "close").loc[date]),
                    }
                except Exception:
                    pass

        # Recalculate total equity
        pos_value = 0.0
        for sym, pos in positions.items():
            if sym in today_prices:
                pos_value += pos["shares"] * today_prices[sym]["close"]
        total_equity = cash + pos_value

        # ═══ 5a. Execute T+1 pending BUYS ═══
        if pending_buys:
            new_pending = []
            for sym, sig_date in pending_buys:
                if sym not in today_prices:
                    new_pending.append((sym, sig_date))
                    continue
                if sym in positions:
                    continue
                exec_price = today_prices[sym]["open"]
                df_sym = stock_data[sym]

                # Limit-up / suspended check
                try:
                    idx = df_sym.index.get_loc(date)
                    if "is_limit_up" in df_sym.columns:
                        if bool(_safe_col(df_sym, "is_limit_up").iloc[idx]):
                            continue
                    if "volume" in df_sym.columns:
                        if float(_safe_col(df_sym, "volume").iloc[idx]) == 0:
                            continue
                except Exception:
                    pass
                # OHLC backup: if low >= open * 1.095, likely limit-up
                if today_prices[sym]["low"] >= exec_price * 1.095:
                    continue

                # Position sizing
                pos_mult = p["regime_pos_mult"].get(state, 0.5)
                per_value = total_equity * p["position_pct"] * pos_mult
                shares = int(per_value / exec_price / 100) * 100
                if shares < 100:
                    continue

                cost = calc_buy_cost(shares, exec_price, p)
                if cost > cash * 0.95:
                    affordable = int(cash * 0.95 / (exec_price * (1 + p["commission_rate"] + p["transfer_fee"])) / 100) * 100
                    if affordable < 100:
                        continue
                    shares = affordable
                    cost = calc_buy_cost(shares, exec_price, p)

                cash -= cost
                positions[sym] = {
                    "entry_date": date,
                    "entry_price": exec_price,
                    "shares": shares,
                    "peak": exec_price,
                    "last_close": exec_price,
                    "entry_regime": state,
                }
                trades.append({
                    "date": date, "symbol": sym, "action": "BUY",
                    "price": exec_price, "shares": shares,
                    "regime": state, "reason": "",
                })
            pending_buys = new_pending

        # ═══ 5b. Execute T+1 pending SELLS ═══
        if pending_sells:
            new_pending_sells = []
            for sym, ratio, reason, queue_date in pending_sells:
                if sym not in positions:
                    continue
                if sym not in today_prices:
                    new_pending_sells.append((sym, ratio, reason, queue_date))
                    continue

                pos = positions[sym]
                df_sym = stock_data[sym]
                days_pending = (date - queue_date).days
                exec_price = today_prices[sym]["open"]

                # Limit-down / suspended check
                suspended = False
                try:
                    idx = df_sym.index.get_loc(date)
                    if "is_limit_down" in df_sym.columns:
                        if bool(_safe_col(df_sym, "is_limit_down").iloc[idx]):
                            suspended = True
                    if not suspended and "volume" in df_sym.columns:
                        if float(_safe_col(df_sym, "volume").iloc[idx]) == 0:
                            suspended = True
                except Exception:
                    pass
                if today_prices[sym]["high"] <= exec_price * 0.905:
                    suspended = True

                if suspended and days_pending < p["max_pending_days"]:
                    new_pending_sells.append((sym, ratio, reason, queue_date))
                    continue
                if suspended:
                    exec_price = exec_price * 0.95  # force-sell discount

                # Corp action: use previous close
                if reason == "corp_action":
                    try:
                        prev_idx = df_sym.index.get_loc(date) - 1
                        if prev_idx >= 0:
                            exec_price = float(_safe_col(df_sym, "close").iloc[prev_idx])
                    except Exception:
                        pass

                pnl_pct = (exec_price - pos["entry_price"]) / pos["entry_price"]
                shares_to_sell = int(pos["shares"] * ratio / 100) * 100
                if shares_to_sell < 100:
                    shares_to_sell = pos["shares"]
                if shares_to_sell > pos["shares"]:
                    shares_to_sell = pos["shares"]

                proceeds = calc_sell_proceeds(shares_to_sell, exec_price, p)
                cash += proceeds
                pos["shares"] -= shares_to_sell

                trades.append({
                    "date": date, "symbol": sym, "action": "SELL",
                    "price": exec_price, "shares": shares_to_sell,
                    "reason": reason, "pnl_pct": pnl_pct,
                    "regime": pos.get("entry_regime", "N/A"),
                    "entry_date": pos["entry_date"],
                })

                if pos["shares"] <= 0:
                    del positions[sym]
            pending_sells = new_pending_sells

        # ═══ 5c. Check EXIT signals for holdings ═══
        for sym, pos in list(positions.items()):
            if sym not in today_prices:
                continue
            cur_close = today_prices[sym]["close"]
            cur_high = today_prices[sym]["high"]
            ret = (cur_close - pos["entry_price"]) / pos["entry_price"]
            days_held = (date - pos["entry_date"]).days

            if cur_high > pos["peak"]:
                pos["peak"] = cur_high
            pos["last_close"] = cur_close

            # Corporate action check
            df_sym = stock_data[sym]
            try:
                idx = df_sym.index.get_loc(date)
                is_corp = check_corp_action(df_sym, idx, p["corp_action_th"])
            except Exception:
                is_corp = False

            should_sell = False
            reason = ""

            if is_corp:
                should_sell = True
                reason = "corp_action"
            elif ret >= p["take_profit"]:
                should_sell = True
                reason = "take_profit"
            elif ret <= p["stop_loss"]:
                should_sell = True
                reason = "stop_loss"
            elif days_held >= p["hold_days"]:
                should_sell = True
                reason = "time_stop"
            elif state == "CRASH":
                should_sell = True
                reason = "crash_clear"

            if should_sell:
                # T+1 lock: cannot sell on entry day
                if pos["entry_date"] == date:
                    already = any(x[0] == sym for x in pending_sells)
                    if not already:
                        pending_sells.append((sym, 1.0, reason, date))
                else:
                    exec_price = today_prices[sym]["open"]
                    # Check if limit-down/suspended
                    df_sym = stock_data[sym]
                    suspended = False
                    try:
                        si = df_sym.index.get_loc(date)
                        if "is_limit_down" in df_sym.columns:
                            if bool(_safe_col(df_sym, "is_limit_down").iloc[si]):
                                suspended = True
                        if not suspended and "volume" in df_sym.columns:
                            if float(_safe_col(df_sym, "volume").iloc[si]) == 0:
                                suspended = True
                    except Exception:
                        pass
                    if today_prices[sym]["high"] <= exec_price * 0.905:
                        suspended = True

                    if not suspended:
                        if reason == "corp_action":
                            try:
                                prev_idx = df_sym.index.get_loc(date) - 1
                                if prev_idx >= 0:
                                    exec_price = float(_safe_col(df_sym, "close").iloc[prev_idx])
                            except Exception:
                                pass
                        pnl_pct = (exec_price - pos["entry_price"]) / pos["entry_price"]
                        proceeds = calc_sell_proceeds(pos["shares"], exec_price, p)
                        cash += proceeds
                        trades.append({
                            "date": date, "symbol": sym, "action": "SELL",
                            "price": exec_price, "shares": pos["shares"],
                            "reason": reason, "pnl_pct": pnl_pct,
                            "regime": pos.get("entry_regime", "N/A"),
                            "entry_date": pos["entry_date"],
                        })
                        del positions[sym]
                    else:
                        already = any(x[0] == sym for x in pending_sells)
                        if not already:
                            pending_sells.append((sym, 1.0, reason, date))

        # ═══ 5d. Generate ENTRY signals ═══
        if state != "CRASH":
            held = set(positions.keys())
            pb = set(x[0] for x in pending_buys)
            n_to_buy = p["max_positions"] - len(positions) - len(pending_buys)

            if n_to_buy > 0 and cash > 10000:
                candidates = []
                for sym, df in stock_data.items():
                    if sym in held or sym in pb:
                        continue
                    if trading_set is not None and sym not in trading_set:
                        continue
                    if date not in df.index:
                        continue
                    try:
                        idx = df.index.get_loc(date)
                    except KeyError:
                        continue
                    if idx < 10:
                        continue

                    # Filters: ST, suspended, extreme recent moves
                    try:
                        if "is_st" in df.columns:
                            if bool(_safe_col(df, "is_st").iloc[idx]):
                                continue
                        if "volume" in df.columns:
                            if float(_safe_col(df, "volume").iloc[idx]) == 0:
                                continue
                    except Exception:
                        pass
                    if not check_recent_extreme(df, idx, p["corp_action_th"]):
                        continue

                    # Signal A: MR
                    has_main = mr_signals[sym].iloc[idx] == 1 if sym in mr_signals else False
                    has_sec = (state == "BULL" and sym in mr_secondary
                               and mr_secondary[sym].iloc[idx] == 1 and not has_main)

                    if has_main:
                        rsi6 = float(_safe_col(df, "RSI6").iloc[idx])
                        candidates.append((sym, 0, rsi6, "main"))
                    elif has_sec:
                        rsi6 = float(_safe_col(df, "RSI6").iloc[idx])
                        candidates.append((sym, 1, rsi6, "secondary"))

                # Signal B: Trend (fill remaining slots)
                if enable_trend and len(candidates) < n_to_buy:
                    for sym, df in stock_data.items():
                        if sym in held or sym in pb:
                            continue
                        if trading_set is not None and sym not in trading_set:
                            continue
                        if date not in df.index:
                            continue
                        try:
                            idx = df.index.get_loc(date)
                        except KeyError:
                            continue
                        if idx < 21:
                            continue
                        # Filters
                        try:
                            if "is_st" in df.columns:
                                if bool(_safe_col(df, "is_st").iloc[idx]):
                                    continue
                            if "volume" in df.columns:
                                if float(_safe_col(df, "volume").iloc[idx]) == 0:
                                    continue
                        except Exception:
                            pass
                        if not check_recent_extreme(df, idx, p["corp_action_th"]):
                            continue

                        # Already in MR candidates?
                        if any(c[0] == sym for c in candidates):
                            continue

                        if sym in trend_signals and trend_signals[sym].iloc[idx] == 1:
                            c = float(_safe_col(df, "close").iloc[idx])
                            candidates.append((sym, 2, 99.0, "trend"))

                # Sort: priority (MR main > MR secondary > Trend), then RSI asc
                candidates.sort(key=lambda x: (x[1], x[2]))
                for cand in candidates[:n_to_buy]:
                    pending_buys.append((cand[0], date))

        # ═══ 5e. Record equity ═══
        pos_value = 0.0
        for sym, pos in positions.items():
            if sym in today_prices:
                pos_value += pos["shares"] * today_prices[sym]["close"]
        equity = cash + pos_value
        equity_curve.append({
            "date": date, "equity": equity, "state": state,
            "n_positions": len(positions), "cash": cash,
        })

    # ═══════════════════════════════════════════════════════════════════
    # 6. Compute metrics
    # ═══════════════════════════════════════════════════════════════════
    logger.info("=== Step 6: Computing metrics ===")
    eq_df = pd.DataFrame(equity_curve).set_index("date")
    init_cap = p["initial_capital"]
    total_return = float(eq_df["equity"].iloc[-1] / init_cap - 1)
    n_years = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
    annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

    cummax = eq_df["equity"].cummax()
    drawdown_series = (eq_df["equity"] - cummax) / cummax
    max_dd = float(drawdown_series.min())

    daily_ret = eq_df["equity"].pct_change().dropna()
    volatility = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) > 0 else 0
    down_ret = daily_ret[daily_ret < 0]
    downside_vol = float(down_ret.std() * np.sqrt(252)) if len(down_ret) > 0 else 0
    sharpe = (annual_return - 0.025) / volatility if volatility > 0 else 0
    sortino = (annual_return - 0.025) / downside_vol if downside_vol > 0 else 0
    calmar = annual_return / abs(max_dd) if max_dd < 0 else 0

    # Trade metrics
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        buys = trades_df[trades_df["action"] == "BUY"]
        sells = trades_df[trades_df["action"] == "SELL"]
        n_trades = len(sells)
        n_buys = len(buys)

        # Pair trades
        paired = []
        for sym, grp in trades_df.groupby("symbol"):
            b = grp[grp["action"] == "BUY"].sort_values("date")
            s = grp[grp["action"] == "SELL"].sort_values("date")
            for i in range(min(len(b), len(s))):
                pnl = (s.iloc[i]["price"] - b.iloc[i]["price"]) / b.iloc[i]["price"]
                paired.append({
                    "pnl_pct": pnl,
                    "entry_date": b.iloc[i]["date"],
                    "exit_date": s.iloc[i]["date"],
                    "symbol": sym,
                    "reason": s.iloc[i].get("reason", ""),
                    "regime": b.iloc[i].get("regime", "N/A"),
                })
        paired_df = pd.DataFrame(paired)
        win_rate = float((paired_df["pnl_pct"] > 0).mean()) if len(paired_df) > 0 else 0
        avg_pnl = float(paired_df["pnl_pct"].mean()) if len(paired_df) > 0 else 0
        avg_win = float(paired_df[paired_df["pnl_pct"] > 0]["pnl_pct"].mean()) if len(paired_df) > 0 else 0
        avg_loss = float(paired_df[paired_df["pnl_pct"] <= 0]["pnl_pct"].mean()) if len(paired_df) > 0 else 0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    else:
        n_trades = n_buys = win_rate = avg_pnl = avg_win = avg_loss = 0
        profit_loss_ratio = 0
        paired_df = pd.DataFrame()

    # Yearly
    yearly = []
    prev = init_cap
    for d, val in eq_df["equity"].resample("YE").last().items():
        yearly.append({"year": d.year, "return": float(val / prev - 1)})
        prev = val

    # Monthly
    monthly = []
    prev_m = init_cap
    for d, val in eq_df["equity"].resample("ME").last().items():
        monthly.append({"year": d.year, "month": d.month, "return": float(val / prev_m - 1)})
        prev_m = val

    # Regime stats
    regime_stats = []
    if len(paired_df) > 0:
        for regime, grp in paired_df.groupby("regime"):
            n = len(grp)
            wr = float((grp["pnl_pct"] > 0).mean())
            cum = float(grp["pnl_pct"].sum())
            avg = float(grp["pnl_pct"].mean())
            regime_stats.append({
                "regime": regime, "n_trades": n, "win_rate": wr,
                "avg_pnl": avg, "cumulative_pnl": cum,
            })

    # Sell reason distribution
    sell_reasons = []
    if not trades_df.empty:
        sells_only = trades_df[trades_df["action"] == "SELL"]
        reason_counts = Counter(sells_only["reason"].fillna("unknown"))
        total_sells = len(sells_only)
        for reason, count in reason_counts.most_common():
            sell_reasons.append({
                "reason": reason, "count": count,
                "pct": count / total_sells * 100 if total_sells > 0 else 0,
            })

    metrics = {
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": max_dd,
        "volatility": volatility,
        "downside_volatility": downside_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "n_years": n_years,
        "n_trades": n_trades,
        "n_buys": n_buys,
        "win_rate": win_rate,
        "avg_pnl_per_trade": avg_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_loss_ratio": profit_loss_ratio,
        "final_equity": float(eq_df["equity"].iloc[-1]),
        "initial_capital": init_cap,
        "elapsed_seconds": time.time() - t0,
    }

    result = {
        "equity_curve": eq_df,
        "daily_returns": daily_ret,
        "trades_df": trades_df,
        "paired_trades": paired_df,
        "metrics": metrics,
        "yearly": yearly,
        "monthly": monthly,
        "regime_stats": regime_stats,
        "sell_reasons": sell_reasons,
        "params": p,
        "start": start,
        "end": end,
        "detection_pool": detection_pool,
        "trading_pool": trading_pool,
        "n_detection": len(detection_codes),
        "n_trading": len(trading_set) if trading_set else len(detection_codes),
        "n_stocks_loaded": len(stock_data),
        "trend_enabled": enable_trend,
    }

    if verbose:
        print_summary(result)

    return result


def print_summary(result):
    """Print a formatted summary matching the style of JQ output."""
    m = result["metrics"]
    print()
    print("=" * 64)
    print("  ATOS MR v6 Dual — Local Backtest Results")
    print("=" * 64)
    print(f"  Period:       {result['start']} → {result['end']} ({m['n_years']:.1f} years)")
    print(f"  Detection:    {result['detection_pool']} ({result['n_detection']} codes)")
    print(f"  Trading:      {result['trading_pool']} ({result['n_trading']} codes)")
    print(f"  Loaded:       {result['n_stocks_loaded']} stocks")
    print(f"  Trend signal: {'ON' if result['trend_enabled'] else 'OFF'}")
    print("-" * 64)
    print(f"  Final Equity: {m['final_equity']:,.0f}")
    print(f"  Total Return: {m['total_return']*100:+.2f}%")
    print(f"  Annual Return:{m['annual_return']*100:+.2f}%")
    print(f"  Max Drawdown: {m['max_drawdown']*100:+.2f}%")
    print(f"  Volatility:   {m['volatility']*100:.2f}%")
    print(f"  Sharpe:       {m['sharpe_ratio']:.3f}")
    print(f"  Sortino:      {m['sortino_ratio']:.3f}")
    print(f"  Calmar:       {m['calmar_ratio']:.3f}")
    print("-" * 64)
    print(f"  Trades:       {m['n_trades']}")
    print(f"  Win Rate:     {m['win_rate']*100:.1f}%")
    print(f"  Avg PnL:      {m['avg_pnl_per_trade']*100:+.3f}%")
    print(f"  Avg Win:      {m['avg_win']*100:+.3f}%")
    print(f"  Avg Loss:     {m['avg_loss']*100:+.3f}%")
    print(f"  P/L Ratio:    {m['profit_loss_ratio']:.2f}")
    print("-" * 64)
    print("  Yearly Returns:")
    for y in result["yearly"]:
        print(f"    {y['year']}: {y['return']*100:+.2f}%")
    print("-" * 64)
    if result["regime_stats"]:
        print("  By Entry Regime:")
        for rs in sorted(result["regime_stats"], key=lambda x: -x["n_trades"]):
            print(f"    {rs['regime']:<15} {rs['n_trades']:>4d} trades  "
                  f"WR={rs['win_rate']:.1%}  avg={rs['avg_pnl']*100:+.2f}%  "
                  f"cum={rs['cumulative_pnl']*100:+.2f}%")
    print("-" * 64)
    if result["sell_reasons"]:
        print("  Sell Reasons:")
        for sr in result["sell_reasons"]:
            print(f"    {sr['reason']:<15} {sr['count']:>4d} ({sr['pct']:.0f}%)")
    print("-" * 64)
    print(f"  Time: {m['elapsed_seconds']:.1f}s")
    print("=" * 64)


def save_results(result, output_dir):
    """Save all detailed data to disk for later comparison."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    logger.info(f"Saving results to {out}")

    # 1. Equity curve
    result["equity_curve"].to_csv(out / "equity_curve.csv", float_format="%.2f")

    # 2. Trades
    if not result["trades_df"].empty:
        result["trades_df"].to_csv(out / "trades.csv", index=False, float_format="%.4f")

    # 3. Paired trades
    if not result["paired_trades"].empty:
        result["paired_trades"].to_csv(out / "paired_trades.csv", index=False, float_format="%.4f")

    # 4. Yearly returns
    pd.DataFrame(result["yearly"]).to_csv(out / "yearly_returns.csv", index=False)

    # 5. Monthly returns
    pd.DataFrame(result["monthly"]).to_csv(out / "monthly_returns.csv", index=False)

    # 6. Summary JSON
    summary = {
        **result["metrics"],
        "start": result["start"],
        "end": result["end"],
        "detection_pool": result["detection_pool"],
        "trading_pool": result["trading_pool"],
        "n_stocks_loaded": result["n_stocks_loaded"],
        "trend_enabled": result["trend_enabled"],
    }
    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    # 7. Regime stats
    if result["regime_stats"]:
        pd.DataFrame(result["regime_stats"]).to_csv(out / "regime_stats.csv", index=False)

    # 8. Sell reasons
    if result["sell_reasons"]:
        pd.DataFrame(result["sell_reasons"]).to_csv(out / "sell_reasons.csv", index=False)

    # 9. Daily returns
    result["daily_returns"].to_csv(out / "daily_returns.csv", float_format="%.6f",
                                    header=["daily_return"])

    # 10. Params
    with open(out / "params.json", "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in result["params"].items() if not callable(v)},
                  f, indent=2, ensure_ascii=False, default=str)

    # 11. Comparison guide
    guide = """# Comparison Guide: Local vs JQ Results

## File Mapping

| Local File | JQ Equivalent |
|-----------|---------------|
| equity_curve.csv | JQ daily equity export |
| trades.csv | JQ trade log |
| yearly_returns.csv | JQ annual return column |
| summary.json | JQ performance summary |
| regime_stats.csv | Per-regime breakdown |
| sell_reasons.csv | Exit reason distribution |

## Key Metrics to Compare

1. **Annual Return** — should be within ±5pp (local has more friction modeled)
2. **Max Drawdown** — should be close (±2pp)
3. **Win Rate** — should be close (±3pp)
4. **Trade Count** — local may have fewer (stricter suspension checks)
5. **Yearly Returns** — compare year-by-year pattern
6. **Sell Reason Distribution** — check if exit patterns match

## Expected Differences

- Local may be slightly lower due to:
  - More conservative limit-up/down detection
  - Transfer fee (0.001%) included
  - Stricter delisting checks
  - Data source differences (复权方式)

- JQ may differ due to:
  - Different stock universe snapshots (JQ uses real-time composition)
  - Different RSI implementation (Wilder vs EMA)
  - Different suspension/pause detection

## How to Add JQ Results

1. Export JQ backtest results as CSV/JSON
2. Save to `reports/ATOS_MR_v6/jq_results/`
3. Run `python scripts/compare_v6.py` to generate comparison report
"""
    with open(out / "comparison_guide.md", "w", encoding="utf-8") as f:
        f.write(guide)

    logger.info(f"All results saved to {out}")
    return out


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="ATOS MR v6 Dual — Local Backtest (mirrors JQ ATOS_MR_v6_Dual.py)"
    )
    parser.add_argument("--start", default="2018-01-01", help="Start date")
    parser.add_argument("--end", default="2022-12-31", help="End date")
    parser.add_argument("--detection-pool", default="ALL",
                        choices=["ALL", "HS300", "CSI1000", "CYB_STAR_50", "HS300_CYB50"],
                        help="Detection universe (default: ALL = HS300+CSI1000+CYB_STAR_50)")
    parser.add_argument("--trading-pool", default="HS300_CYB50",
                        choices=["HS300_CYB50", "ALL", "HS300", "CSI1000", "CYB_STAR_50", "SAME"],
                        help="Trading universe restriction (default: HS300_CYB50)")
    parser.add_argument("--output", default="reports/ATOS_MR_v6/local_detailed",
                        help="Output directory for detailed results")
    parser.add_argument("--no-trend", action="store_true",
                        help="Disable trend signal (MR-only baseline)")
    parser.add_argument("--max-pos", type=int, default=22, help="Max positions")
    parser.add_argument("--pos-pct", type=float, default=0.17, help="Position size (fraction)")
    parser.add_argument("--hold", type=int, default=8, help="Hold days")
    parser.add_argument("--tp", type=float, default=0.30, help="Take profit threshold")
    parser.add_argument("--sl", type=float, default=-0.02, help="Stop loss threshold")
    parser.add_argument("--capital", type=float, default=1_000_000, help="Initial capital")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    # Build params
    params = dict(JQ_PARAMS)
    params["max_positions"] = args.max_pos
    params["position_pct"] = args.pos_pct
    params["hold_days"] = args.hold
    params["take_profit"] = args.tp
    params["stop_loss"] = args.sl
    params["initial_capital"] = args.capital

    result = run_backtest(
        start=args.start,
        end=args.end,
        detection_pool=args.detection_pool,
        trading_pool=args.trading_pool,
        params=params,
        enable_trend=not args.no_trend,
        verbose=not args.quiet,
    )

    save_results(result, args.output)


if __name__ == "__main__":
    main()
