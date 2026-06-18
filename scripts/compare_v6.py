#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ATOS MR v6 Dual — Local vs JQ Comparison Script

Compares local backtest results (from local_v6_dual.py) with
JoinQuant platform results (saved by user).

Usage:
    python scripts/compare_v6.py
    python scripts/compare_v6.py --local reports/ATOS_MR_v6/local_detailed
    python scripts/compare_v6.py --jq reports/ATOS_MR_v6/jq_results
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_local_results(local_dir):
    """Load local backtest results from directory."""
    local = Path(local_dir)
    if not local.exists():
        return None

    result = {}
    # Summary
    summary_file = local / "summary.json"
    if summary_file.exists():
        with open(summary_file) as f:
            result["summary"] = json.load(f)

    # Equity curve
    eq_file = local / "equity_curve.csv"
    if eq_file.exists():
        result["equity"] = pd.read_csv(eq_file, index_col=0, parse_dates=True)

    # Yearly
    yr_file = local / "yearly_returns.csv"
    if yr_file.exists():
        result["yearly"] = pd.read_csv(yr_file)

    # Monthly
    mo_file = local / "monthly_returns.csv"
    if mo_file.exists():
        result["monthly"] = pd.read_csv(mo_file)

    # Trades
    tr_file = local / "trades.csv"
    if tr_file.exists():
        result["trades"] = pd.read_csv(tr_file, parse_dates=["date"])

    # Paired trades
    pt_file = local / "paired_trades.csv"
    if pt_file.exists():
        result["paired"] = pd.read_csv(pt_file, parse_dates=["entry_date", "exit_date"])

    # Regime stats
    rs_file = local / "regime_stats.csv"
    if rs_file.exists():
        result["regime_stats"] = pd.read_csv(rs_file)

    # Sell reasons
    sr_file = local / "sell_reasons.csv"
    if sr_file.exists():
        result["sell_reasons"] = pd.read_csv(sr_file)

    return result if result else None


def load_jq_results(jq_dir):
    """Load JQ platform results.

    The user should save JQ output files with these expected names:
    - jq_summary.json     — manually created from JQ performance page
    - jq_equity.csv       — daily equity from JQ export
    - jq_trades.csv       — trade log from JQ export
    - jq_yearly.csv       — annual returns

    If these don't exist, the script will look for any CSV/JSON files.
    """
    jq = Path(jq_dir)
    if not jq.exists():
        return None

    result = {}

    # Try standard names first, then fall back to any files
    summary_file = jq / "jq_summary.json"
    if summary_file.exists():
        with open(summary_file) as f:
            result["summary"] = json.load(f)

    eq_file = jq / "jq_equity.csv"
    if eq_file.exists():
        result["equity"] = pd.read_csv(eq_file, index_col=0, parse_dates=True)

    yr_file = jq / "jq_yearly.csv"
    if yr_file.exists():
        result["yearly"] = pd.read_csv(yr_file)

    tr_file = jq / "jq_trades.csv"
    if tr_file.exists():
        result["trades"] = pd.read_csv(tr_file, parse_dates=["date"])

    return result if result else None


def compare(local, jq):
    """Produce a structured comparison between local and JQ results."""
    if not local or not local.get("summary"):
        print("ERROR: No local results found. Run local_v6_dual.py first.")
        return

    if not jq or not jq.get("summary"):
        print("=" * 72)
        print("  LOCAL RESULTS ONLY (JQ results not yet available)")
        print("=" * 72)
        print_local_summary(local)
        print()
        print("To add JQ results:")
        print("  1. Export JQ backtest data to reports/ATOS_MR_v6/jq_results/")
        print("  2. Run this script again for comparison")
        return

    # Both available — full comparison
    ls = local["summary"]
    js = jq["summary"]

    print("=" * 72)
    print("  ATOS MR v6 Dual — Local vs JQ Comparison")
    print("=" * 72)

    # ═══ Core Metrics ═══
    metrics_map = [
        ("Annual Return", "annual_return", "{:+.2f}%", 100),
        ("Total Return", "total_return", "{:+.2f}%", 100),
        ("Max Drawdown", "max_drawdown", "{:+.2f}%", 100),
        ("Volatility", "volatility", "{:.2f}%", 100),
        ("Sharpe Ratio", "sharpe_ratio", "{:.3f}", 1),
        ("Sortino Ratio", "sortino_ratio", "{:.3f}", 1),
        ("Calmar Ratio", "calmar_ratio", "{:.3f}", 1),
        ("Win Rate", "win_rate", "{:.1f}%", 100),
        ("P/L Ratio", "profit_loss_ratio", "{:.2f}", 1),
        ("Trade Count", "n_trades", "{:.0f}", 1),
        ("Avg PnL/Trade", "avg_pnl_per_trade", "{:+.3f}%", 100),
        ("Final Equity", "final_equity", "{:,.0f}", 1),
    ]

    print()
    print(f"  {'Metric':<20} {'Local':>12} {'JQ':>12} {'Diff':>12} {'Status':>10}")
    print("  " + "-" * 66)

    for label, key, fmt, mult in metrics_map:
        lv = ls.get(key, np.nan)
        jv = js.get(key, np.nan)

        if key.endswith("_return") or key in ("win_rate", "avg_pnl_per_trade", "max_drawdown"):
            diff = (lv - jv)  # already in decimal
        elif key == "n_trades":
            diff = lv - jv
        elif key == "final_equity":
            diff = lv - jv
        elif key == "profit_loss_ratio":
            diff = lv - jv
        else:
            diff = lv - jv

        # Status
        tolerance_map = {
            "annual_return": 0.05, "max_drawdown": 0.03, "volatility": 0.03,
            "sharpe_ratio": 0.5, "win_rate": 0.05, "n_trades": 999,
        }
        tol = tolerance_map.get(key, 999)
        if abs(diff) <= tol:
            status = "✓"
        elif np.isnan(diff):
            status = "N/A"
        else:
            status = "⚠"

        l_str = fmt.format(lv * mult) if not np.isnan(lv) else "N/A"
        j_str = fmt.format(jv * mult) if not np.isnan(jv) else "N/A"
        d_str = fmt.format(diff * mult) if not np.isnan(diff) else "N/A"

        print(f"  {label:<20} {l_str:>12} {j_str:>12} {d_str:>12} {status:>10}")

    print()

    # ═══ Yearly Returns ═══
    if local.get("yearly") is not None and jq.get("yearly") is not None:
        print("  Yearly Returns:")
        ly = local["yearly"]
        jy = jq["yearly"]
        ly_dict = {row["year"]: row["return"] for _, row in ly.iterrows()}
        jy_dict = {row["year"]: row["return"] for _, row in jy.iterrows()}
        all_years = sorted(set(ly_dict.keys()) | set(jy_dict.keys()))
        print(f"  {'Year':<8} {'Local':>10} {'JQ':>10} {'Diff':>10}")
        print("  " + "-" * 42)
        for yr in all_years:
            lv = ly_dict.get(yr, np.nan)
            jv = jy_dict.get(yr, np.nan)
            diff = lv - jv
            l_str = f"{lv*100:+.2f}%" if not np.isnan(lv) else "N/A"
            j_str = f"{jv*100:+.2f}%" if not np.isnan(jv) else "N/A"
            d_str = f"{diff*100:+.2f}%" if not np.isnan(diff) else "N/A"
            status = "✓" if abs(diff) < 0.08 else "⚠"
            print(f"  {yr:<8} {l_str:>10} {j_str:>10} {d_str:>10} {status}")
        print()

    # ═══ Regime Stats ═══
    if local.get("regime_stats") is not None:
        print("  Local — By Entry Regime:")
        rs = local["regime_stats"]
        print(f"  {'Regime':<15} {'Trades':>6} {'Win Rate':>9} {'Avg PnL':>9} {'Cum PnL':>9}")
        print("  " + "-" * 54)
        for _, row in rs.iterrows():
            print(f"  {row['regime']:<15} {int(row['n_trades']):>6} "
                  f"{row['win_rate']*100:>8.1f}% {row['avg_pnl']*100:>+8.2f}% "
                  f"{row['cumulative_pnl']*100:>+8.2f}%")
        print()

    # ═══ Sell Reasons ═══
    if local.get("sell_reasons") is not None:
        print("  Local — Sell Reason Distribution:")
        sr = local["sell_reasons"]
        for _, row in sr.iterrows():
            print(f"    {row['reason']:<15} {int(row['count']):>5} ({row['pct']:.0f}%)")
        print()

    # ═══ Equity Curve Correlation ═══
    if local.get("equity") is not None and jq.get("equity") is not None:
        leq = local["equity"]
        jeq = jq["equity"]
        # Align on dates
        common_dates = leq.index.intersection(jeq.index)
        if len(common_dates) > 100:
            l_aligned = leq.loc[common_dates, "equity"]
            j_aligned = jeq.loc[common_dates, "equity"]
            corr = l_aligned.pct_change().corr(j_aligned.pct_change())
            print(f"  Daily Return Correlation: {corr:.4f}")
            if corr < 0.7:
                print("  ⚠ Low correlation — strategy implementations may differ significantly")
            elif corr < 0.9:
                print("  Moderate correlation — some differences in execution")
            else:
                print("  ✓ High correlation — implementations are consistent")
            print()

    print("=" * 72)


def print_local_summary(local):
    """Print a summary of just the local results."""
    ls = local["summary"]
    print()
    print(f"  Period:       {ls.get('start','?')} → {ls.get('end','?')} ({ls.get('n_years',0):.1f}y)")
    print(f"  Detection:    {ls.get('detection_pool','?')}")
    print(f"  Trading:      {ls.get('trading_pool','?')}")
    print(f"  Stocks loaded:{ls.get('n_stocks_loaded','?')}")
    print(f"  Trend signal: {'ON' if ls.get('trend_enabled') else 'OFF'}")
    print(f"  Time:         {ls.get('elapsed_seconds',0):.1f}s")
    print()
    for label, key, fmt, mult in [
        ("Annual Return", "annual_return", "{:+.2f}%", 100),
        ("Max Drawdown", "max_drawdown", "{:+.2f}%", 100),
        ("Sharpe Ratio", "sharpe_ratio", "{:.3f}", 1),
        ("Sortino Ratio", "sortino_ratio", "{:.3f}", 1),
        ("Win Rate", "win_rate", "{:.1f}%", 100),
        ("P/L Ratio", "profit_loss_ratio", "{:.2f}", 1),
        ("Trades", "n_trades", "{:.0f}", 1),
    ]:
        v = ls.get(key, np.nan)
        s = fmt.format(v * mult) if not np.isnan(v) else "N/A"
        print(f"  {label:<20} {s}")

    if local.get("yearly") is not None:
        print()
        print("  Yearly:")
        for _, row in local["yearly"].iterrows():
            print(f"    {int(row['year'])}: {row['return']*100:+.2f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Compare local vs JQ ATOS MR v6 Dual results"
    )
    parser.add_argument("--local", default="reports/ATOS_MR_v6/local_detailed",
                        help="Local results directory")
    parser.add_argument("--jq", default="reports/ATOS_MR_v6/jq_results",
                        help="JQ results directory")
    args = parser.parse_args()

    local = load_local_results(args.local)
    jq = load_jq_results(args.jq)

    if not local:
        print(f"ERROR: No local results at {args.local}")
        print("Run: python scripts/local_v6_dual.py")
        sys.exit(1)

    compare(local, jq)


if __name__ == "__main__":
    main()
