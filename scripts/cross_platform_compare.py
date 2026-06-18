#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Full cross-platform comparison: JQ vs Local ATOS MR v6 Dual.
Parses JQ transaction.csv + result CSV + position.csv,
runs local backtest for same period, produces multi-dimension comparison.
"""
import csv
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

JQ_DIR = PROJECT_ROOT / "JQ" / "compareV6" / "JQData"
OUT_DIR = PROJECT_ROOT / "JQ" / "compareV6" / "localData"


def read_gbk_csv(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ["gb18030", "gbk"]:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")


def parse_jq_result():
    """Parse JQ result CSV → metrics dict."""
    text = read_gbk_csv(JQ_DIR / "result_1 (4).csv")
    reader = csv.reader(io.StringIO(text))
    next(reader)  # header
    rows = []
    for r in reader:
        if len(r) < 8:
            continue
        rows.append({
            "time": pd.Timestamp(r[0]),
            "bench_cum": float(r[1]),
            "strat_cum": float(r[2]),
            "daily_profit": float(r[3]),
            "daily_loss": float(r[4]),
            "daily_buy": float(r[5]),
            "daily_sell": float(r[6]),
            "excess_pct": float(r[7]) if len(r) > 7 else 0,
        })
    df = pd.DataFrame(rows).set_index("time")

    # Reconstruct equity from PnL (the strat_cum appears to be cumulative %)
    # Verify: day 1 strat_cum = -0.16, daily_loss = -478.13
    # If initial capital = X, then -478.13/X = -0.0016 → X = 298,831
    # But first daily column shows various values. Let's use strat_cum directly.
    init_cap = 300000  # from position.csv first Cash row
    final_equity = init_cap * (1 + df["strat_cum"].iloc[-1] / 100)

    n_years = (df.index[-1] - df.index[0]).days / 365.25
    total_ret = df["strat_cum"].iloc[-1] / 100
    annual_ret = (1 + total_ret) ** (1 / n_years) - 1

    # Equity from daily PnL
    equity = [init_cap]
    for _, row in df.iterrows():
        pnl = row["daily_profit"] + row["daily_loss"]
        equity.append(equity[-1] + pnl)
    eq_series = pd.Series(equity[1:], index=df.index)
    dd = (eq_series / eq_series.cummax() - 1).min()
    daily_ret = eq_series.pct_change().dropna()
    vol = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 0 else 0
    sharpe = (annual_ret - 0.025) / vol if vol > 0 else 0

    # Yearly from resampled equity
    yearly = {}
    prev = init_cap
    for d, val in eq_series.resample("YE").last().items():
        yearly[d.year] = float(val / prev - 1)
        prev = val

    # Monthly
    monthly = {}
    prev_m = init_cap
    for d, val in eq_series.resample("ME").last().items():
        monthly[f"{d.year}-{d.month:02d}"] = float(val / prev_m - 1)
        prev_m = val

    result = {
        "source": "JQ",
        "start": str(df.index[0].date()),
        "end": str(df.index[-1].date()),
        "n_years": n_years,
        "n_days": len(df),
        "init_capital": init_cap,
        "final_equity": final_equity,
        "total_return": total_ret,
        "annual_return": annual_ret,
        "max_drawdown": dd,
        "volatility": vol,
        "sharpe": sharpe,
        "bench_return": df["bench_cum"].iloc[-1] / 100,
        "excess_return": df["excess_pct"].iloc[-1] / 100,
        "total_profit": df["daily_profit"].sum(),
        "total_loss": df["daily_loss"].sum(),
        "net_pnl": df["daily_profit"].sum() + df["daily_loss"].sum(),
        "buy_signal_days": int((df["daily_buy"] > 0).sum()),
        "sell_signal_days": int((df["daily_sell"] > 0).sum()),
        "yearly": yearly,
        "monthly": monthly,
    }
    return result, eq_series, df


def parse_jq_transactions():
    """Parse JQ transaction.csv → trade-level DataFrame."""
    text = read_gbk_csv(JQ_DIR / "transaction.csv")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    # Cols: 0=日期, 1=委托时间, 2=品种, 3=名称, 4=买卖方向, 5=下单类型,
    #        6=成交数量, 7=成交价, 8=成交额, 9=委托数量, 10=委托价格,
    #        11=平仓盈亏, 12=手续费, 13=状态, 14=成交时间

    trades = []
    for r in reader:
        if len(r) < 8:
            continue
        # Extract stock code
        code_match = re.search(r"\((\d+)\.(XSHG|XSHE)\)", r[3]) if len(r) > 3 else None
        if not code_match:
            continue
        sym = code_match.group(1)

        def parse_num(s):
            s = s.strip().replace(",", "").replace("股", "").replace("手", "")
            if "万" in s:
                return float(s.replace("万", "")) * 10000
            try:
                return float(s)
            except ValueError:
                return 0.0

        direction = "BUY" if "买" in r[4] else "SELL"
        qty = parse_num(r[6]) if len(r) > 6 else 0
        price = float(r[7]) if len(r) > 7 and r[7].strip() else 0.0
        amount = float(r[8]) if len(r) > 8 and r[8].strip() else 0.0
        pnl = float(r[11]) if len(r) > 11 and r[11].strip() else 0.0
        fee = float(r[12]) if len(r) > 12 and r[12].strip() else 0.0

        trades.append({
            "date": r[0].strip(),
            "symbol": sym,
            "action": direction,
            "shares": qty,
            "price": price,
            "amount": amount,
            "pnl": pnl,
            "fee": fee,
        })

    df = pd.DataFrame(trades)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def compute_trade_metrics(txn_df):
    """Compute paired trade metrics from JQ transaction log."""
    if txn_df.empty:
        return {}

    buys = txn_df[txn_df["action"] == "BUY"].sort_values("date")
    sells = txn_df[txn_df["action"] == "SELL"].sort_values("date")

    n_buys = len(buys)
    n_sells = len(sells)

    # FIFO pairing per symbol
    sym_buys = defaultdict(list)
    sym_sells = defaultdict(list)
    for _, t in buys.iterrows():
        sym_buys[t["symbol"]].append(t)
    for _, t in sells.iterrows():
        sym_sells[t["symbol"]].append(t)

    paired = []
    for sym in set(list(sym_buys.keys()) + list(sym_sells.keys())):
        b_list = sym_buys.get(sym, [])
        s_list = sym_sells.get(sym, [])
        # Match by date order (FIFO)
        b_idx, s_idx = 0, 0
        while b_idx < len(b_list) and s_idx < len(s_list):
            b = b_list[b_idx]
            s = s_list[s_idx]
            if s["date"] >= b["date"]:
                pnl_pct = (s["price"] / b["price"] - 1) if b["price"] > 0 else 0
                hold = (s["date"] - b["date"]).days
                paired.append({
                    "symbol": sym,
                    "entry_date": b["date"],
                    "exit_date": s["date"],
                    "entry_price": b["price"],
                    "exit_price": s["price"],
                    "pnl_pct": pnl_pct,
                    "hold_days": hold,
                })
                b_idx += 1
                s_idx += 1
            else:
                s_idx += 1

    if not paired:
        return {"n_buys": n_buys, "n_sells": n_sells, "n_paired": 0}

    pdf = pd.DataFrame(paired)
    win_rate = (pdf["pnl_pct"] > 0).mean()
    avg_pnl = pdf["pnl_pct"].mean()
    wins = pdf[pdf["pnl_pct"] > 0]["pnl_pct"]
    losses = pdf[pdf["pnl_pct"] <= 0]["pnl_pct"]
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    yearly = {}
    pdf["year"] = pdf["exit_date"].dt.year
    for yr, grp in pdf.groupby("year"):
        yearly[yr] = {
            "n": len(grp),
            "wr": float((grp["pnl_pct"] > 0).mean()),
            "avg": float(grp["pnl_pct"].mean()),
            "cum": float(grp["pnl_pct"].sum()),
        }

    return {
        "n_buys": n_buys,
        "n_sells": n_sells,
        "n_paired": len(paired),
        "win_rate": float(win_rate),
        "avg_pnl": float(avg_pnl),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "pl_ratio": float(pl_ratio) if pl_ratio != float("inf") else 999,
        "avg_hold_days": float(pdf["hold_days"].mean()),
        "median_hold_days": float(pdf["hold_days"].median()),
        "yearly": yearly,
        "paired_df": pdf,
    }


def parse_jq_positions():
    """Parse JQ position.csv to get per-day equity and holding count."""
    text = read_gbk_csv(JQ_DIR / "position.csv")
    reader = csv.reader(io.StringIO(text))
    next(reader)

    dates_info = defaultdict(lambda: {"n_positions": 0, "total_value": 0, "cash": 0})
    for r in reader:
        if len(r) < 8:
            continue
        date = r[0].strip()
        typ = r[1].strip()

        if not typ:  # Cash
            try:
                cash_col = 15 if len(r) > 15 else 7
                dates_info[date]["cash"] = float(r[cash_col]) if r[cash_col].strip() else 0
            except (ValueError, TypeError):
                pass
        else:
            dates_info[date]["n_positions"] += 1
            try:
                dates_info[date]["total_value"] += float(r[7]) if r[7].strip() else 0
            except (ValueError, TypeError):
                pass

    return dict(dates_info)


def run_local_backtest(start, end):
    """Run local backtest with JQ-matching parameters."""
    from scripts.local_v6_dual import run_backtest

    params = {
        "max_positions": 22,
        "position_pct": 0.17,
        "hold_days": 8,
        "stop_loss": -0.02,
        "take_profit": 0.30,
        "max_pending_days": 20,
        "corp_action_th": 15.0,
        "regime_pos_mult": {
            "BULL": 1.5, "SIDEWAYS": 1.0, "BEAR": 0.2,
            "CHOPPY_BEAR": 0.3, "CRASH": 0.0,
        },
        "trend_ma_period": 20,
        "trend_vol_mult": 1.2,
        "commission_rate": 0.00025,
        "stamp_tax_rate": 0.001,
        "slippage": 0.001,
        "transfer_fee": 0.00001,
        "min_commission": 5.0,
        "initial_capital": 300000.0,
        "regime_lag_days": 3,
    }
    return run_backtest(
        start=start, end=end,
        detection_pool="HS300_CYB50",  # match JQ ALL = HS300 + CYB_STAR_50
        trading_pool="SAME",           # JQ detects and trades from same pool
        params=params,
        enable_trend=True,
        verbose=True,
    )


def build_comparison_table(jq_result, jq_trade_metrics, local_result):
    """Build side-by-side comparison across all dimensions."""
    lm = local_result["metrics"]
    lt = local_result  # has trades_df, paired_trades, etc.

    rows = []

    def add(section, metric, jq_val, local_val, fmt=".2f", higher_better=True):
        try:
            jq_f = float(jq_val) if jq_val is not None else np.nan
        except (TypeError, ValueError):
            jq_f = np.nan
        try:
            lo_f = float(local_val) if local_val is not None else np.nan
        except (TypeError, ValueError):
            lo_f = np.nan

        if np.isnan(jq_f) or np.isnan(lo_f):
            diff = np.nan
        else:
            diff = lo_f - jq_f

        rows.append({
            "section": section,
            "metric": metric,
            "jq": jq_f,
            "local": lo_f,
            "diff": diff,
            "fmt": fmt,
            "higher_better": higher_better,
        })

    # ── Core Performance ──
    add("核心收益", "累计收益", jq_result["total_return"] * 100, lm["total_return"] * 100, ".2f")
    add("核心收益", "年化收益", jq_result["annual_return"] * 100, lm["annual_return"] * 100, ".2f")
    add("核心收益", "最终净值", jq_result["final_equity"], lm["final_equity"], ".0f")
    add("核心收益", "基准(HS300)收益", jq_result["bench_return"] * 100, None, ".2f")

    # ── Risk ──
    add("风险", "最大回撤", jq_result["max_drawdown"] * 100, lm["max_drawdown"] * 100, ".2f", False)
    add("风险", "年化波动率", jq_result.get("volatility", 0) * 100, lm["volatility"] * 100, ".2f", False)
    add("风险", "夏普比率", jq_result.get("sharpe", 0), lm["sharpe_ratio"], ".3f")

    # ── Trade Activity ──
    jq_tm = jq_trade_metrics or {}
    add("交易活跃度", "买入次数", jq_tm.get("n_buys", 0), lm["n_buys"], ".0f")
    add("交易活跃度", "卖出次数", jq_tm.get("n_sells", 0), lm["n_trades"], ".0f")
    add("交易活跃度", "配对交易", jq_tm.get("n_paired", 0), len(local_result.get("paired_trades", pd.DataFrame())), ".0f")
    add("交易活跃度", "交易股票数", None, local_result.get("n_stocks_loaded", 0), ".0f")

    # ── Trade Quality ──
    add("交易质量", "胜率", jq_tm.get("win_rate", 0) * 100, lm["win_rate"] * 100, ".1f")
    add("交易质量", "平均盈亏", jq_tm.get("avg_pnl", 0) * 100, lm["avg_pnl_per_trade"] * 100, ".2f")
    add("交易质量", "平均盈利", jq_tm.get("avg_win", 0) * 100, lm["avg_win"] * 100, ".2f")
    add("交易质量", "平均亏损", jq_tm.get("avg_loss", 0) * 100, lm["avg_loss"] * 100, ".2f")
    add("交易质量", "盈亏比", jq_tm.get("pl_ratio", 0), lm["profit_loss_ratio"], ".2f")
    add("交易质量", "平均持仓(天)", jq_tm.get("avg_hold_days", 0), 8.0, ".1f")  # local is fixed 8d

    return rows


def print_comparison(rows):
    """Pretty-print comparison table."""
    current_section = ""
    for r in rows:
        if r["section"] != current_section:
            current_section = r["section"]
            print(f"\n{'─'*72}")
            print(f"  [{current_section}]")
            print(f"  {'指标':<18} {'JQ':>10} {'本地':>10} {'差异':>10}  {'评价':>12}")
            print(f"  {'-'*60}")

        jq_str = f"{r['jq']:{r['fmt']}}" if not np.isnan(r['jq']) else "N/A"
        lo_str = f"{r['local']:{r['fmt']}}" if not np.isnan(r['local']) else "N/A"

        if np.isnan(r['diff']):
            diff_str = "N/A"
            verdict = "—"
        else:
            diff_str = f"{r['diff']:{r['fmt']}}"
            # Determine if difference is "good" (local better) or not
            abs_diff = abs(r['diff'])
            if r["higher_better"]:
                if r['diff'] > 0.01:  # local meaningfully better
                    verdict = "✓ 本地更优"
                elif r['diff'] < -0.01:
                    verdict = "✗ JQ更优"
                else:
                    verdict = "≈ 持平"
            else:
                if r['diff'] < -0.01:  # local has LESS drawdown/vol
                    verdict = "✓ 本地更优"
                elif r['diff'] > 0.01:
                    verdict = "✗ JQ更优"
                else:
                    verdict = "≈ 持平"

        print(f"  {r['metric']:<18} {jq_str:>10} {lo_str:>10} {diff_str:>10}  {verdict:>12}")


def main():
    t0 = time.time()
    print("=" * 72)
    print("  ATOS MR v6 Dual — 跨平台多维度对比")
    print("=" * 72)

    # ── 1. Parse JQ data ──
    print("\n[1/4] 解析 JQ 平台数据...")
    jq_result, jq_equity, jq_df = parse_jq_result()
    print(f"  JQ: {jq_result['start']} → {jq_result['end']}, "
          f"{jq_result['n_days']} 天, "
          f"累计收益 {jq_result['total_return']*100:+.2f}%")

    jq_txn = parse_jq_transactions()
    print(f"  交易记录: {len(jq_txn)} 条")
    if not jq_txn.empty:
        print(f"    买入: {(jq_txn['action']=='BUY').sum()}, "
              f"卖出: {(jq_txn['action']=='SELL').sum()}")

    jq_trade_metrics = compute_trade_metrics(jq_txn)
    print(f"  配对交易: {jq_trade_metrics.get('n_paired', 0)} 笔")
    if jq_trade_metrics.get('n_paired', 0) > 0:
        print(f"    胜率: {jq_trade_metrics['win_rate']*100:.1f}%, "
              f"盈亏比: {jq_trade_metrics['pl_ratio']:.2f}")

    # ── 2. Run local backtest ──
    print("\n[2/4] 运行本地回测 (匹配 JQ 参数 + 股票池)...")
    local_result = run_local_backtest(jq_result["start"], jq_result["end"])

    lm = local_result["metrics"]
    print(f"  本地: {local_result['start']} → {local_result['end']}, "
          f"累计收益 {lm['total_return']*100:+.2f}%")
    print(f"  交易: {lm['n_trades']} 笔, 胜率 {lm['win_rate']*100:.1f}%")

    # ── 3. Build comparison ──
    print("\n[3/4] 构建多维度对比...")
    comparison_rows = build_comparison_table(jq_result, jq_trade_metrics, local_result)

    # ── 4. Output ──
    print("\n[4/4] 输出对比结果...")
    print_comparison(comparison_rows)

    # Yearly comparison
    print(f"\n{'─'*72}")
    print(f"  [年度收益对比]")
    print(f"  {'年份':<8} {'JQ':>10} {'本地':>10} {'差异':>10}")
    print(f"  {'-'*42}")
    jq_yearly = jq_result.get("yearly", {})
    local_yearly = {}
    if local_result.get("yearly"):
        for y in local_result["yearly"]:
            local_yearly[y["year"]] = y["return"]
    all_years = sorted(set(list(jq_yearly.keys()) + list(local_yearly.keys())))
    for yr in all_years:
        jv = jq_yearly.get(yr, np.nan)
        lv = local_yearly.get(yr, np.nan)
        diff = lv - jv if not np.isnan(jv) and not np.isnan(lv) else np.nan
        j_str = f"{jv*100:+.2f}%" if not np.isnan(jv) else "N/A"
        l_str = f"{lv*100:+.2f}%" if not np.isnan(lv) else "N/A"
        d_str = f"{diff*100:+.2f}pp" if not np.isnan(diff) else "N/A"
        print(f"  {yr:<8} {j_str:>10} {l_str:>10} {d_str:>10}")

    # Monthly correlation
    jq_monthly = jq_result.get("monthly", {})
    local_monthly = {}
    if local_result.get("monthly"):
        for m in local_result["monthly"]:
            local_monthly[f"{m['year']}-{m['month']:02d}"] = m["return"]
    common_months = sorted(set(jq_monthly.keys()) & set(local_monthly.keys()))
    if len(common_months) > 12:
        jq_m = [jq_monthly[k] for k in common_months]
        lo_m = [local_monthly[k] for k in common_months]
        monthly_corr = np.corrcoef(jq_m, lo_m)[0, 1]
        print(f"\n  月度收益相关性: {monthly_corr:.4f} "
              f"({'高度一致' if monthly_corr > 0.8 else '中度相关' if monthly_corr > 0.5 else '低相关'})")

    # Daily correlation
    local_eq = local_result["equity_curve"]
    if "equity" in local_eq.columns:
        local_daily = local_eq["equity"].pct_change().dropna()
        jq_daily = jq_equity.pct_change().dropna()
        common_idx = local_daily.index.intersection(jq_daily.index)
        if len(common_idx) > 100:
            corr = local_daily.loc[common_idx].corr(jq_daily.loc[common_idx])
            print(f"  日收益相关性: {corr:.4f} "
                  f"({'高度一致' if corr > 0.8 else '中度相关' if corr > 0.5 else '低相关'})")

    # ── Save ──
    out_data = {
        "jq_result": {k: v for k, v in jq_result.items() if k not in ("yearly", "monthly")},
        "jq_yearly": {str(k): v for k, v in jq_result.get("yearly", {}).items()},
        "jq_trade_metrics": {k: v for k, v in (jq_trade_metrics or {}).items()
                             if k != "paired_df"},
        "local_summary": {k: v for k, v in lm.items() if not callable(v)},
        "comparison_rows": [{k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                             for k, v in r.items()} for r in comparison_rows],
    }
    out_path = OUT_DIR / "cross_platform_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n对比结果已保存: {out_path}")

    elapsed = time.time() - t0
    print(f"总耗时: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
