#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Reconstruct all JQ trades from position.csv (7808 daily holding snapshots).

Logic:
  - New stock appears (cur_qty > 0, prev_qty = 0) → BUY
  - Stock disappears (cur_qty = 0, prev_qty > 0) → SELL
  - FIFO pairing per symbol to compute PnL, holding period, etc.
"""
import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

POSITION_FILE = PROJECT_ROOT / "JQ" / "compareV6" / "JQData" / "position.csv"


def parse_qty(s):
    """Parse quantity strings with Chinese units."""
    s = s.strip().replace(",", "")
    if "万" in s:
        return float(s.replace("万", "")) * 10000
    if "手" in s:
        return float(s.replace("手", "")) * 100
    if "股" in s:
        return float(s.replace("股", ""))
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def main():
    # ── Read raw position.csv ──
    with open(POSITION_FILE, "rb") as f:
        raw = f.read()

    # Detect encoding
    for enc in ["gb18030", "gbk", "gb2312", "utf-8"]:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    print(f"Header: {header}")

    # Column mapping (from raw inspection):
    # Col 0: date      Col 4: 今仓(today pos)    Col 8: daily PnL
    # Col 1: type      Col 5: 昨仓(yest pos)     Col 9: entry price (cost basis)
    # Col 2: name      Col 6: close price        Col 12: cumulative PnL
    # Col 3: direction Col 7: market value       Col 13: trade qty today
    #                                           Col 15: total equity

    positions_by_date = defaultdict(dict)  # date -> {code: props}
    cash_by_date = {}

    for r in reader:
        if len(r) < 8:
            continue
        date = r[0].strip()
        typ = r[1].strip()
        name = r[2].strip()

        if not typ:  # Cash row
            try:
                equity_col = 15 if len(r) > 15 else 7
                cash_by_date[date] = float(r[equity_col]) if r[equity_col].strip() else 0.0
            except (ValueError, TypeError):
                pass
            continue

        # Extract stock code: e.g. "浩丰科技(300419.XSHE)" -> "300419"
        code_match = re.search(r"\((\d+)\.(XSHG|XSHE)\)", name)
        if not code_match:
            continue
        stock_code = code_match.group(1)

        # Col 4 = 今仓 (today's position), Col 5 = 昨仓 (yesterday's position)
        today_qty = parse_qty(r[4]) if len(r) > 4 else 0
        yest_qty = parse_qty(r[5]) if len(r) > 5 else 0
        try:
            close_price = float(r[6]) if r[6].strip() else 0.0
        except (ValueError, TypeError):
            close_price = 0.0
        try:
            mkt_value = float(r[7]) if r[7].strip() else 0.0
        except (ValueError, TypeError):
            mkt_value = 0.0
        # Col 9 = cost basis (entry price)
        try:
            cost_basis = float(r[9]) if len(r) > 9 and r[9].strip() and r[9].strip() != "-" else 0.0
        except (ValueError, TypeError):
            cost_basis = 0.0
        # Col 13 = traded qty today
        trade_qty = parse_qty(r[13]) if len(r) > 13 else 0
        # Col 12 = cumulative PnL
        try:
            cum_pnl = float(r[12]) if len(r) > 12 and r[12].strip() else 0.0
        except (ValueError, TypeError):
            cum_pnl = 0.0

        positions_by_date[date][stock_code] = {
            "today_qty": today_qty,
            "yest_qty": yest_qty,
            "close": close_price,
            "mkt_value": mkt_value,
            "cost_basis": cost_basis,
            "trade_qty": trade_qty,
            "cum_pnl": cum_pnl,
            "name": name,
        }

    dates = sorted(positions_by_date.keys())
    print(f"Parsed: {len(dates)} trading days, {dates[0]} -> {dates[-1]}")
    print(f"Cash records: {len(cash_by_date)}")

    # ── Reconstruct trades from position changes ──
    # BUY: yest_qty=0, today_qty>0 → new position opened at cost_basis
    # SELL: yest_qty>0, today_qty=0 → position closed at close price
    trades = []
    holdings = {}  # {symbol: {entry_date, entry_price, shares, peak}}

    for date in dates:
        today_pos = positions_by_date.get(date, {})

        for sym, pos in today_pos.items():
            if pos["today_qty"] > 0 and pos["yest_qty"] == 0:
                # BUY: new position
                shares = pos["today_qty"]
                entry = pos["cost_basis"] if pos["cost_basis"] > 0 else pos["close"]
                holdings[sym] = {
                    "entry_date": date,
                    "entry_price": entry,
                    "shares": shares,
                    "peak": pos["close"],
                }
                trades.append({
                    "date": date, "symbol": sym, "action": "BUY",
                    "price": entry, "shares": shares, "pnl": 0.0,
                })
            elif pos["today_qty"] == 0 and pos["yest_qty"] > 0:
                # SELL: position closed
                exit_price = pos["close"]
                if sym in holdings:
                    h = holdings[sym]
                    pnl = (exit_price / h["entry_price"] - 1) if h["entry_price"] > 0 else 0
                    hold_days = (pd.Timestamp(date) - pd.Timestamp(h["entry_date"])).days
                else:
                    pnl = 0.0
                    hold_days = 0
                trades.append({
                    "date": date, "symbol": sym, "action": "SELL",
                    "price": exit_price, "shares": pos["yest_qty"],
                    "pnl": pnl, "entry_date": holdings.get(sym, {}).get("entry_date", "?"),
                    "hold_days": hold_days,
                })
                if sym in holdings:
                    del holdings[sym]
            elif sym in holdings and pos["today_qty"] > 0:
                # Update peak
                if pos["close"] > holdings[sym]["peak"]:
                    holdings[sym]["peak"] = pos["close"]

    buys = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    print(f"\nReconstructed: {len(buys)} BUYs, {len(sells)} SELLs")

    # ── FIFO pairing ──
    symbol_buys = defaultdict(list)
    symbol_sells = defaultdict(list)
    for t in trades:
        if t["action"] == "BUY":
            symbol_buys[t["symbol"]].append(t)
        else:
            symbol_sells[t["symbol"]].append(t)

    paired = []
    for sym in set(list(symbol_buys.keys()) + list(symbol_sells.keys())):
        b_list = sorted(symbol_buys.get(sym, []), key=lambda x: x["date"])
        s_list = sorted(symbol_sells.get(sym, []), key=lambda x: x["date"])
        for i in range(min(len(b_list), len(s_list))):
            b = b_list[i]
            s = s_list[i]
            pnl_pct = (s["price"] / b["price"] - 1) if b["price"] > 0 else 0
            hold_days = (pd.Timestamp(s["date"]) - pd.Timestamp(b["date"])).days
            paired.append(
                {
                    "symbol": sym,
                    "entry_date": b["date"],
                    "exit_date": s["date"],
                    "entry_price": b["price"],
                    "exit_price": s["price"],
                    "pnl_pct": pnl_pct,
                    "hold_days": hold_days,
                    "shares": b["shares"],
                }
            )

    print(f"\n=== JQ Reconstructed Trade Metrics ===")
    print(f"Paired trades: {len(paired)}")
    if not paired:
        print("WARNING: No paired trades found — position format may differ")
        return

    pdf = pd.DataFrame(paired)
    win_rate = (pdf["pnl_pct"] > 0).mean()
    avg_pnl = pdf["pnl_pct"].mean()
    wins = pdf[pdf["pnl_pct"] > 0]["pnl_pct"]
    losses = pdf[pdf["pnl_pct"] <= 0]["pnl_pct"]
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    avg_hold = pdf["hold_days"].mean()

    print(f"Win Rate:     {win_rate*100:.1f}%")
    print(f"Avg PnL:      {avg_pnl*100:+.2f}%")
    print(f"Avg Win:      {avg_win*100:+.2f}%")
    print(f"Avg Loss:     {avg_loss*100:+.2f}%")
    print(f"P/L Ratio:    {pl_ratio:.2f}")
    print(f"Avg Hold:     {avg_hold:.1f} days")
    print(f"Median Hold:  {pdf['hold_days'].median():.0f} days")
    print(f"Unique stocks:{pdf['symbol'].nunique()}")

    # ── Holding period distribution ──
    print(f"\nHolding Period Distribution:")
    for th in [1, 3, 5, 8, 10, 15, 20, 30]:
        pct = (pdf["hold_days"] <= th).mean() * 100
        print(f"  <= {th:2d}d: {pct:5.1f}%")

    # ── PnL distribution ──
    print(f"\nPnL Distribution:")
    bins = [-0.10, -0.05, -0.03, -0.02, 0, 0.02, 0.05, 0.10, 0.30]
    for th in bins:
        pct = (pdf["pnl_pct"] <= th).mean() * 100
        print(f"  <= {th*100:+.0f}%: {pct:5.1f}%")

    # ── Yearly breakdown ──
    pdf["year"] = pd.to_datetime(pdf["exit_date"]).dt.year
    print(f"\nYearly Breakdown:")
    for yr, grp in pdf.groupby("year"):
        wr = (grp["pnl_pct"] > 0).mean() * 100
        print(
            f"  {yr}: {len(grp):4d} trades, WR={wr:.1f}%, "
            f"Avg={grp['pnl_pct'].mean()*100:+.2f}%, "
            f"Cum={grp['pnl_pct'].sum()*100:+.2f}%"
        )

    # ── Monthly PnL ──
    pdf["exit_month"] = pd.to_datetime(pdf["exit_date"]).dt.to_period("M")
    monthly = pdf.groupby("exit_month").agg(
        n_trades=("pnl_pct", "count"),
        total_pnl=("pnl_pct", "sum"),
        win_rate=("pnl_pct", lambda x: (x > 0).mean()),
    )
    print(f"\nMonthly Summary (first 5 & last 5):")
    for idx in list(range(5)) + list(range(len(monthly) - 5, len(monthly))):
        if 0 <= idx < len(monthly):
            r = monthly.iloc[idx]
            print(
                f"  {monthly.index[idx]}: {int(r['n_trades']):3d} trades, "
                f"WR={r['win_rate']*100:.0f}%, PnL={r['total_pnl']*100:+.2f}%"
            )

    # ── PnL per day (to compare with result CSV) ──
    daily_pnl = pdf.groupby("exit_date")["pnl_pct"].sum()
    total_pnl_sum = pdf["pnl_pct"].sum()
    print(f"\nTotal cumulative PnL (sum of all trade returns): {total_pnl_sum*100:+.2f}%")

    # ── Save ──
    out_dir = PROJECT_ROOT / "JQ" / "compareV6" / "JQData"
    pdf.to_csv(out_dir / "reconstructed_trades.csv", index=False, float_format="%.6f")

    # Also save summary JSON
    import json
    summary = {
        "n_trades": len(paired),
        "win_rate": float(win_rate),
        "avg_pnl": float(avg_pnl),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "pl_ratio": float(pl_ratio) if pl_ratio != float("inf") else 999,
        "avg_hold_days": float(avg_hold),
        "median_hold_days": float(pdf["hold_days"].median()),
        "unique_symbols": int(pdf["symbol"].nunique()),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "yearly": {
            str(yr): {
                "n": int(len(grp)),
                "wr": float((grp["pnl_pct"] > 0).mean()),
                "avg": float(grp["pnl_pct"].mean()),
                "cum": float(grp["pnl_pct"].sum()),
            }
            for yr, grp in pdf.groupby("year")
        },
    }
    with open(out_dir / "reconstructed_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_dir / 'reconstructed_trades.csv'}")
    print(f"Saved: {out_dir / 'reconstructed_summary.json'}")


if __name__ == "__main__":
    main()
