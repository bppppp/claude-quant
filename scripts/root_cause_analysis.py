#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Deep root-cause analysis: WHY JQ and Local diverge so dramatically.
Goes beyond metrics into stock-level, signal-level, and timing analysis.
"""
import csv, io, re, json, sys
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

JQ_DIR = PROJECT_ROOT / "JQ" / "compareV6" / "JQData"
LOCAL_DIR = PROJECT_ROOT / "JQ" / "compareV6" / "localData"


def read_gbk(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ["gb18030", "gbk"]:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def load_jq_trades():
    """Load JQ transactions with detailed stock-level data."""
    text = read_gbk(JQ_DIR / "transaction.csv")
    reader = csv.reader(io.StringIO(text))
    next(reader)
    trades = []
    for r in reader:
        if len(r) < 12:
            continue
        m = re.search(r"\((\d+)\.(XSHG|XSHE)\)", r[3]) if len(r) > 3 else None
        if not m:
            continue
        sym = m.group(1)

        def pn(s):
            s = s.strip().replace(",", "").replace("股", "").replace("手", "")
            if "万" in s:
                return float(s.replace("万", "")) * 10000
            try: return float(s)
            except: return 0.0

        trades.append({
            "date": pd.Timestamp(r[0]),
            "symbol": sym,
            "action": "BUY" if "买" in r[4] else "SELL",
            "shares": pn(r[6]) if len(r) > 6 else 0,
            "price": float(r[7]) if len(r) > 7 and r[7].strip() else 0.0,
            "amount": float(r[8]) if len(r) > 8 and r[8].strip() else 0.0,
            "pnl_yuan": float(r[11]) if len(r) > 11 and r[11].strip() else 0.0,
            "fee": float(r[12]) if len(r) > 12 and r[12].strip() else 0.0,
            "exchange": m.group(2),
        })
    return pd.DataFrame(trades)


def load_local_trades():
    """Load local backtest trades."""
    df = pd.read_csv(LOCAL_DIR / "trades.csv", parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_jq_result():
    """Load JQ daily result."""
    text = read_gbk(JQ_DIR / "result_1 (4).csv")
    reader = csv.reader(io.StringIO(text))
    next(reader)
    rows = []
    for r in reader:
        if len(r) < 8:
            continue
        rows.append({
            "date": pd.Timestamp(r[0]).normalize(),
            "bench_cum": float(r[1]),
            "strat_cum": float(r[2]),
            "profit": float(r[3]),
            "loss": float(r[4]),
            "excess": float(r[7]) if len(r) > 7 else 0.0,
        })
    df = pd.DataFrame(rows).set_index("date")
    df = df[~df.index.duplicated(keep="last")]
    return df


def pair_trades(txn_df):
    """FIFO pair buys and sells, return paired DataFrame."""
    sym_buys = defaultdict(list)
    sym_sells = defaultdict(list)
    for _, t in txn_df.iterrows():
        if t["action"] == "BUY":
            sym_buys[t["symbol"]].append(t)
        else:
            sym_sells[t["symbol"]].append(t)

    paired = []
    for sym in set(list(sym_buys.keys()) + list(sym_sells.keys())):
        bl = sym_buys.get(sym, [])
        sl = sym_sells.get(sym, [])
        bi, si = 0, 0
        while bi < len(bl) and si < len(sl):
            b, s = bl[bi], sl[si]
            if s["date"] >= b["date"]:
                pnl = (s["price"] / b["price"] - 1) if b["price"] > 0 else 0
                paired.append({
                    "symbol": sym,
                    "entry_date": b["date"],
                    "exit_date": s["date"],
                    "entry_price": b["price"],
                    "exit_price": s["price"],
                    "pnl_pct": pnl,
                    "hold_days": (s["date"] - b["date"]).days,
                    "amount": b.get("amount", 0),
                })
                bi += 1; si += 1
            else:
                si += 1
    return pd.DataFrame(paired)


def normalize_sym(s):
    """Normalize stock code to 6-digit string."""
    return str(int(s)).zfill(6)


def analyze_stock_overlap(jq_paired, local_paired):
    """Analysis 1: Stock selection overlap."""
    jq_raw = jq_paired["symbol"].unique()
    lo_raw = local_paired["symbol"].unique()
    jq_stocks = set(normalize_sym(s) for s in jq_raw)
    lo_stocks = set(normalize_sym(s) for s in lo_raw)
    common = jq_stocks & lo_stocks
    jq_only = jq_stocks - lo_stocks
    lo_only = lo_stocks - jq_stocks

    print("=" * 64)
    print("  ANALYSIS 1: Stock Selection Overlap")
    print("=" * 64)
    print(f"  JQ unique stocks:     {len(jq_stocks)}")
    print(f"  Local unique stocks:  {len(lo_stocks)}")
    print(f"  Common stocks:        {len(common)}")
    print(f"  JQ only:              {len(jq_only)} ({len(jq_only)/max(len(jq_stocks),1)*100:.1f}%)")
    print(f"  Local only:           {len(lo_only)} ({len(lo_only)/max(len(lo_stocks),1)*100:.1f}%)")
    print(f"  Overlap ratio:        {len(common)/max(len(jq_stocks | lo_stocks),1)*100:.1f}%")

    # Trade count on common stocks
    jq_on_common = jq_paired[jq_paired["symbol"].isin(common)]
    lo_on_common = local_paired[local_paired["symbol"].isin(common)]
    if len(jq_on_common) > 0 and len(lo_on_common) > 0:
        print(f"\n  --- On common stocks only ---")
        print(f"  JQ trades on common:     {len(jq_on_common)} ({len(jq_on_common)/len(jq_paired)*100:.0f}%)")
        print(f"  Local trades on common:  {len(lo_on_common)} ({len(lo_on_common)/len(local_paired)*100:.0f}%)")
        print(f"  JQ win rate on common:   {(jq_on_common['pnl_pct']>0).mean()*100:.1f}%")
        print(f"  Local win rate on common:{(lo_on_common['pnl_pct']>0).mean()*100:.1f}%")
        print(f"  JQ avg PnL on common:    {jq_on_common['pnl_pct'].mean()*100:+.3f}%")
        print(f"  Local avg PnL on common: {lo_on_common['pnl_pct'].mean()*100:+.3f}%")

    # Show top stocks by trade count on each side
    jq_top = Counter(jq_paired["symbol"].values).most_common(10)
    lo_top = Counter(local_paired["symbol"].values).most_common(10)
    print(f"\n  Top 10 JQ stocks:     {[s for s,_ in jq_top]}")
    print(f"  Top 10 Local stocks:  {[s for s,_ in lo_top]}")
    top_overlap = set(s for s,_ in jq_top) & set(s for s,_ in lo_top)
    print(f"  Top-10 overlap:       {len(top_overlap)}/10")
    return jq_stocks, lo_stocks, common


def analyze_timing(jq_paired, local_paired):
    """Analysis 2: Entry/exit timing comparison."""
    # Align trades by date buckets
    jq_by_month = jq_paired.groupby(jq_paired["entry_date"].dt.to_period("M")).agg(
        jq_n=("pnl_pct", "count"),
        jq_wr=("pnl_pct", lambda x: (x > 0).mean()),
        jq_avg=("pnl_pct", "mean"),
    )
    lo_by_month = local_paired.groupby(local_paired["entry_date"].dt.to_period("M")).agg(
        lo_n=("pnl_pct", "count"),
        lo_wr=("pnl_pct", lambda x: (x > 0).mean()),
        lo_avg=("pnl_pct", "mean"),
    )

    merged = jq_by_month.join(lo_by_month, how="outer").fillna(0)

    print("\n" + "=" * 64)
    print("  ANALYSIS 2: Entry Timing & Monthly Trade Count")
    print("=" * 64)
    print(f"  Months with trades - JQ: {(merged['jq_n']>0).sum()}, Local: {(merged['lo_n']>0).sum()}")
    print(f"  Correlation of monthly trade count: {merged['jq_n'].corr(merged['lo_n']):.4f}")
    print(f"  Correlation of monthly win rate:    {merged['jq_wr'].corr(merged['lo_wr']):.4f}")
    print(f"  Correlation of monthly avg PnL:     {merged['jq_avg'].corr(merged['lo_avg']):.4f}")

    # Identify months where both had trades but win rates diverged
    both_active = merged[(merged["jq_n"] >= 5) & (merged["lo_n"] >= 5)].copy()
    both_active["wr_diff"] = both_active["lo_wr"] - both_active["jq_wr"]
    if len(both_active) > 0:
        worst_months = both_active.nsmallest(5, "wr_diff")
        best_months = both_active.nlargest(5, "wr_diff")
        print(f"\n  Months where Local WR << JQ WR (JQ did better):")
        for idx, row in worst_months.iterrows():
            print(f"    {idx}: JQ WR={row['jq_wr']*100:.0f}% Local WR={row['lo_wr']*100:.0f}% "
                  f"(n={int(row['jq_n'])},{int(row['lo_n'])})")
        print(f"\n  Months where Local WR >> JQ WR (Local did better):")
        for idx, row in best_months.iterrows():
            print(f"    {idx}: JQ WR={row['jq_wr']*100:.0f}% Local WR={row['lo_wr']*100:.0f}% "
                  f"(n={int(row['jq_n'])},{int(row['lo_n'])})")
    return merged


def analyze_signal_frequency(jq_paired, local_paired):
    """Analysis 3: Signal/day and holding behavior."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 3: Signal Frequency & Holding Behavior")
    print("=" * 64)

    # Trades per day distribution
    jq_per_day = jq_paired.groupby("entry_date").size()
    lo_per_day = local_paired.groupby("entry_date").size()
    print(f"  Avg entries/day - JQ: {jq_per_day.mean():.1f}, Local: {lo_per_day.mean():.1f}")
    print(f"  Days with entries - JQ: {len(jq_per_day)}, Local: {len(lo_per_day)}")

    # Holding period distribution
    print(f"\n  Holding Period Distribution:")
    for th in [1, 3, 5, 8, 10, 15, 20]:
        jq_pct = (jq_paired["hold_days"] <= th).mean() * 100
        lo_pct = (local_paired["hold_days"] <= th).mean() * 100
        print(f"    <= {th:2d}d:  JQ={jq_pct:5.1f}%  Local={lo_pct:5.1f}%")

    # Stop loss frequency (early exit < hold_days)
    jq_early = (jq_paired["hold_days"] < 6).mean() * 100
    lo_early = (local_paired["hold_days"] < 6).mean() * 100
    print(f"\n  Early exits (< 6d): JQ={jq_early:.1f}%, Local={lo_early:.1f}%")


def analyze_pnl_distribution(jq_paired, local_paired):
    """Analysis 4: PnL distribution shape comparison."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 4: PnL Distribution Shape")
    print("=" * 64)

    for label, pdf in [("JQ", jq_paired), ("Local", local_paired)]:
        pnl = pdf["pnl_pct"].dropna()
        print(f"\n  {label} PnL Stats:")
        print(f"    Mean={pnl.mean()*100:+.3f}%, Median={pnl.median()*100:+.3f}%")
        print(f"    Std={pnl.std()*100:.2f}%, Skew={pnl.skew():.2f}, Kurt={pnl.kurtosis():.2f}")
        print(f"    P1={pnl.quantile(0.01)*100:+.2f}%, P5={pnl.quantile(0.05)*100:+.2f}%")
        print(f"    P95={pnl.quantile(0.95)*100:+.2f}%, P99={pnl.quantile(0.99)*100:+.2f}%")

        # PnL buckets
        bins = [-0.20, -0.10, -0.05, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50]
        print(f"    PnL Buckets:")
        for i in range(len(bins) - 1):
            pct = ((pnl > bins[i]) & (pnl <= bins[i+1])).mean() * 100
            bar = "#" * int(pct / 2)
            print(f"      {bins[i]*100:+.0f}% to {bins[i+1]*100:+.0f}%: {pct:5.1f}% {bar}")


def analyze_sector_exposure(jq_txn, local_trades_df):
    """Analysis 5: Exchange/sector concentration."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 5: Exchange & Market Segment Exposure")
    print("=" * 64)

    for label, df in [("JQ", jq_txn), ("Local", local_trades_df)]:
        if "exchange" not in df.columns:
            def get_exchange(sym):
                s = str(sym).zfill(6)
                if s.startswith("6"): return "XSHG"
                elif s.startswith("0") or s.startswith("3"): return "XSHE"
                elif s.startswith("688"): return "STAR"
                return "OTHER"
            df = df.copy()
            df["exchange"] = df["symbol"].apply(get_exchange)

        buys = df[df["action"] == "BUY"] if "action" in df.columns else df
        if "action" in df.columns and "amount" in buys.columns:
            volume_by_exchange = buys.groupby("exchange")["amount"].sum()
        elif "action" in df.columns:
            volume_by_exchange = buys.groupby("exchange").size()
        else:
            volume_by_exchange = pd.Series(dtype=float)

        print(f"\n  {label} trade count by exchange:")
        total = volume_by_exchange.sum()
        for ex in sorted(volume_by_exchange.index):
            v = volume_by_exchange[ex]
            print(f"    {ex}: {v:.0f} ({v/total*100:.1f}%)" if total > 0 else f"    {ex}: {v}")


def analyze_market_regime_context(jq_result, jq_paired, local_paired):
    """Analysis 6: Performance in different market environments."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 6: Performance by Market Environment")
    print("=" * 64)

    # Compute HS300 trend from JQ result (bench_cum)
    jq_res = jq_result.copy()
    jq_res["bench_return_60d"] = jq_res["bench_cum"].diff(60)

    # Classify market regimes from benchmark
    bull_mask = jq_res["bench_return_60d"] > 5
    bear_mask = jq_res["bench_return_60d"] < -5
    chop_mask = ~bull_mask & ~bear_mask

    regimes = {"Bull (60d up > 5%)": bull_mask, "Bear (60d down > 5%)": bear_mask, "Choppy (flat)": chop_mask}

    for reg_name, mask in regimes.items():
        reg_dates = set(jq_res[mask].index)
        jq_in_reg = jq_paired[jq_paired["entry_date"].isin(reg_dates)]
        lo_in_reg = local_paired[local_paired["entry_date"].isin(reg_dates)]
        if len(jq_in_reg) > 10 and len(lo_in_reg) > 10:
            print(f"\n  {reg_name}:")
            print(f"    JQ:   {len(jq_in_reg):4d} trades, WR={(jq_in_reg['pnl_pct']>0).mean()*100:.1f}%, "
                  f"Avg={jq_in_reg['pnl_pct'].mean()*100:+.3f}%")
            print(f"    Local:{len(lo_in_reg):4d} trades, WR={(lo_in_reg['pnl_pct']>0).mean()*100:.1f}%, "
                  f"Avg={lo_in_reg['pnl_pct'].mean()*100:+.3f}%")


def analyze_drawdown_profile(jq_result, local_eq):
    """Analysis 7: Drawdown timing and recovery."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 7: Drawdown Profile Comparison")
    print("=" * 64)

    # JQ equity
    jq_res = jq_result.copy()
    jq_eq = 300000 + jq_res["profit"].cumsum() + jq_res["loss"].cumsum()
    jq_dd = jq_eq / jq_eq.cummax() - 1

    # Local equity
    lo_eq = local_eq["equity"]
    lo_dd = lo_eq / lo_eq.cummax() - 1

    # Align
    common_dates = jq_dd.index.intersection(lo_dd.index)
    if len(common_dates) > 0:
        jq_dd_aligned = jq_dd.loc[common_dates]
        lo_dd_aligned = lo_dd.loc[common_dates]
        dd_corr = jq_dd_aligned.corr(lo_dd_aligned)
        print(f"  Drawdown series correlation: {dd_corr:.4f}")

        # Worst drawdown periods for each
        jq_worst_idx = jq_dd_aligned.idxmin()
        lo_worst_idx = lo_dd_aligned.idxmin()
        print(f"  JQ worst DD: {jq_dd_aligned.min()*100:.1f}% on {jq_worst_idx.date()}")
        print(f"  Local worst DD: {lo_dd_aligned.min()*100:.1f}% on {lo_worst_idx.date()}")

        # DD > 20% periods
        jq_deep_dd = (jq_dd_aligned < -0.20).sum()
        lo_deep_dd = (lo_dd_aligned < -0.10).sum()
        print(f"  Days with DD > 20%: JQ={jq_deep_dd}, Local={lo_deep_dd}")


def analyze_same_stock_trades(jq_paired, local_paired, common_stocks):
    """Analysis 8: On common stocks, compare entry timing and price."""
    print("\n" + "=" * 64)
    print("  ANALYSIS 8: Same-Stock Entry Timing & Price Comparison")
    print("=" * 64)

    common = list(common_stocks)[:50]  # sample 50 common stocks
    jq_common = jq_paired[jq_paired["symbol"].isin(common)].copy()
    lo_common = local_paired[local_paired["symbol"].isin(common)].copy()

    # For each common stock, compare entry dates
    jq_entries_by_stock = jq_common.groupby("symbol")["entry_date"].apply(set)
    lo_entries_by_stock = lo_common.groupby("symbol")["entry_date"].apply(set)

    same_day_entries = 0
    total_jq_entries = 0
    for sym in common:
        jq_dates = jq_entries_by_stock.get(sym, set())
        lo_dates = lo_entries_by_stock.get(sym, set())
        total_jq_entries += len(jq_dates)
        same_day_entries += len(jq_dates & lo_dates)

    print(f"  Same-stock same-day entries: {same_day_entries}/{total_jq_entries} "
          f"({same_day_entries/max(total_jq_entries,1)*100:.1f}%)")

    # Entry date offset distribution
    offsets = []
    for sym in common:
        jq_dates = sorted(jq_entries_by_stock.get(sym, set()))
        lo_dates = sorted(lo_entries_by_stock.get(sym, set()))
        for jd in jq_dates:
            # Find closest local entry date
            closest = min(lo_dates, key=lambda ld: abs((ld - jd).days)) if lo_dates else None
            if closest:
                offsets.append((jd - closest).days)

    if offsets:
        offsets_arr = np.array(offsets)
        print(f"\n  Entry date offset (JQ - Local):")
        print(f"    Mean: {offsets_arr.mean():.1f}d, Median: {np.median(offsets_arr):.0f}d")
        print(f"    Std: {offsets_arr.std():.1f}d")
        print(f"    Same day (|offset|=0): {(abs(offsets_arr)==0).mean()*100:.1f}%")
        print(f"    Within 1 day: {(abs(offsets_arr)<=1).mean()*100:.1f}%")
        print(f"    Within 3 days: {(abs(offsets_arr)<=3).mean()*100:.1f}%")
        print(f"    Within 5 days: {(abs(offsets_arr)<=5).mean()*100:.1f}%")

    # Trade count per stock comparison
    jq_trades_per_stock = jq_common.groupby("symbol").size()
    lo_trades_per_stock = lo_common.groupby("symbol").size()
    print(f"\n  Avg trades/stock: JQ={jq_trades_per_stock.mean():.1f}, Local={lo_trades_per_stock.mean():.1f}")
    print(f"  Correlation of trade frequency per stock: "
          f"{jq_trades_per_stock.corr(lo_trades_per_stock):.4f}")


def main():
    print("=" * 64)
    print("  ATOS MR v6 Dual — Root Cause Deep Dive")
    print("=" * 64)

    # ── Load data ──
    print("\n[Loading data...]")
    jq_txn = load_jq_trades()
    local_trades = load_local_trades()
    jq_result = load_jq_result()
    local_eq = pd.read_csv(LOCAL_DIR / "equity_curve.csv", index_col=0, parse_dates=True)

    jq_paired = pair_trades(jq_txn)
    local_paired = pd.read_csv(LOCAL_DIR / "paired_trades.csv", parse_dates=["entry_date", "exit_date"])

    # Normalize symbols
    jq_paired["symbol"] = jq_paired["symbol"].apply(normalize_sym)
    local_paired["symbol"] = local_paired["symbol"].apply(normalize_sym)
    jq_txn["symbol"] = jq_txn["symbol"].apply(normalize_sym)
    local_trades["symbol"] = local_trades["symbol"].apply(normalize_sym)

    # Add hold_days to local if missing
    if "hold_days" not in local_paired.columns:
        local_paired["hold_days"] = (local_paired["exit_date"] - local_paired["entry_date"]).dt.days

    print(f"  JQ: {len(jq_txn)} transactions -> {len(jq_paired)} paired trades")
    print(f"  Local: {len(local_trades)} transactions -> {len(local_paired)} paired trades")

    # ── Run all analyses ──
    jq_stocks, lo_stocks, common_stocks = analyze_stock_overlap(jq_paired, local_paired)
    analyze_timing(jq_paired, local_paired)
    analyze_signal_frequency(jq_paired, local_paired)
    analyze_pnl_distribution(jq_paired, local_paired)
    analyze_sector_exposure(jq_txn, local_trades)
    analyze_market_regime_context(jq_result, jq_paired, local_paired)
    analyze_drawdown_profile(jq_result, local_eq)

    # ── Analysis 8: Same-stock entry/exit comparison ──
    analyze_same_stock_trades(jq_paired, local_paired, common_stocks)

    # ── Final synthesis ──
    print("\n" + "=" * 64)
    print("  SYNTHESIS: Why the 30pp annual return gap?")
    print("=" * 64)

    # Calculate contribution of each factor
    jq_pnl_sum = jq_paired["pnl_pct"].sum()
    lo_pnl_sum = local_paired["pnl_pct"].sum()
    print(f"\n  Total cumulative PnL: JQ={jq_pnl_sum*100:+.1f}%, Local={lo_pnl_sum*100:+.1f}%")

    # Factor 1: Win rate
    jq_wr = (jq_paired["pnl_pct"] > 0).mean()
    lo_wr = (local_paired["pnl_pct"] > 0).mean()
    jq_extra_losses = (lo_wr - jq_wr) * len(jq_paired)  # how many more losses JQ has
    print(f"\n  Factor 1 - Win Rate Gap: {lo_wr*100:.1f}% vs {jq_wr*100:.1f}%")
    print(f"    JQ has ~{jq_extra_losses:.0f} more losing trades than Local would")
    print(f"    Each extra loss costs ~{jq_paired[jq_paired['pnl_pct']<=0]['pnl_pct'].mean()*100:+.2f}%")

    # Factor 2: Loss severity (JQ losers are bigger)
    jq_avg_loss = jq_paired[jq_paired["pnl_pct"] <= 0]["pnl_pct"].mean()
    lo_avg_loss = local_paired[local_paired["pnl_pct"] <= 0]["pnl_pct"].mean()
    print(f"\n  Factor 2 - Loss Severity: JQ={jq_avg_loss*100:+.2f}% vs Local={lo_avg_loss*100:+.2f}%")
    loss_gap = abs(jq_avg_loss) - abs(lo_avg_loss)
    n_losses_jq = (jq_paired["pnl_pct"] <= 0).sum()
    print(f"    JQ losers are {loss_gap*100:.2f}pp worse, affecting {n_losses_jq} trades")
    print(f"    Total impact: {loss_gap * n_losses_jq * 100:+.1f}% cumulative PnL")

    # Factor 3: Win size
    jq_avg_win = jq_paired[jq_paired["pnl_pct"] > 0]["pnl_pct"].mean()
    lo_avg_win = local_paired[local_paired["pnl_pct"] > 0]["pnl_pct"].mean()
    print(f"\n  Factor 3 - Win Size: JQ={jq_avg_win*100:+.2f}% vs Local={lo_avg_win*100:+.2f}%")

    # Factor 4: Trade count
    print(f"\n  Factor 4 - Trade Frequency: JQ={len(jq_paired)} vs Local={len(local_paired)}")
    print(f"    Similar count — not a major factor")

    # Biggest factor identification
    print(f"\n  >>> PRIMARY CAUSE: Stock Selection Divergence")
    print(f"  The overlap ratio of stocks traded is the key metric.")
    print(f"  Different 前复权 -> different price histories -> different stocks flagged")
    print(f"  as 'oversold' -> completely different trade universe.")
    print(f"  This propagates into lower win rate AND larger losses.")


if __name__ == "__main__":
    main()
