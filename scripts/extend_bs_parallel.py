#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extend baostock data 2012-2017 — 2 workers + resume + retry.

Features:
- Resume: checkpoint file tracks completed stocks, Ctrl+C safe
- 2 parallel workers, each with own baostock connection
- Failed stocks retried 3 times, then by orchestrator
- Indices downloaded first (fast, single-process)
"""
import os, sys, time, json, csv, io, re, signal
from pathlib import Path
from collections import defaultdict
from multiprocessing import Process, Queue
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

START_DATE = "2012-01-01"
END_DATE = "2017-12-31"
STOCK_DIR = PROJECT_ROOT / "data" / "data-by-stock-bs"
DAY_DIR = PROJECT_ROOT / "data" / "data-by-day-bs"
CHECKPOINT_FILE = STOCK_DIR / "_checkpoint.json"

INDICES = {"sh.000300": "hs300", "sh.000852": "csi1000", "sh.000016": "sse50"}

COLUMNS = [
    "日期", "代码", "名称", "所属行业", "开盘价", "最高价", "最低价", "收盘价",
    "前收盘价", "成交量（股）", "成交额（元）", "换手率", "涨幅%", "振幅%",
    "是否ST", "量比", "3日涨幅%", "6日涨幅%", "10日涨幅%", "25日涨幅%",
    "是否涨停", "总股本（股）", "流通股本（股）", "总市值（元）", "流通市值（元）",
    "静态市盈率", "市净率", "静态市销率", "5日均线", "10日均线", "20日均线",
    "30日均线", "60日均线", "120日均线", "250日均线", "上市时间", "退市时间",
    "是否融资融券",
]

MIN_PRE2018_ROWS = 100  # skip if stock already has this many pre-2018 rows


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_checkpoint(done_set):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(sorted(done_set), f)
    tmp.replace(CHECKPOINT_FILE)


def already_done(sym):
    """Check if this stock already has sufficient pre-2018 data."""
    csv_path = STOCK_DIR / f"{sym}.csv"
    if not csv_path.exists():
        return False
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=MIN_PRE2018_ROWS + 10)
        df["日期"] = pd.to_datetime(df["日期"])
        pre_count = (df["日期"] < "2018-01-01").sum()
        return pre_count >= MIN_PRE2018_ROWS
    except Exception:
        return False


def compute_derived(df):
    c, h, l, v = df["收盘价"], df["最高价"], df["最低价"], df["成交量（股）"]
    df["前收盘价"] = c.shift(1)
    df["涨幅%"] = (c / df["前收盘价"] - 1) * 100
    df["振幅%"] = (h - l) / df["前收盘价"] * 100
    if "换手率" not in df.columns or df["换手率"].isna().all():
        df["换手率"] = np.nan
    for p, col in [(3, "3日涨幅%"), (6, "6日涨幅%"), (10, "10日涨幅%"), (25, "25日涨幅%")]:
        df[col] = (c / c.shift(p) - 1) * 100
    df["量比"] = v / v.rolling(5).mean()
    df["是否涨停"] = df["涨幅%"] >= 9.5
    for p, col in [(5, "5日均线"), (10, "10日均线"), (20, "20日均线"),
                   (30, "30日均线"), (60, "60日均线"), (120, "120日均线"), (250, "250日均线")]:
        df[col] = c.rolling(p).mean()
    return df


def download_one(bs, code_bs, name, start, end, is_index=False):
    """Download single stock/index, return DataFrame or None."""
    try:
        rs = bs.query_history_k_data_plus(
            code_bs, "date,code,open,high,low,close,volume,amount",
            start_date=start, end_date=end,
            frequency="d", adjustflag="3",
        )
        if rs.error_code != "0":
            return None
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["日期", "代码", "开盘价", "最高价",
                                          "最低价", "收盘价", "成交量（股）", "成交额（元）"])
        for col in ["开盘价", "最高价", "最低价", "收盘价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["成交量（股）"] = pd.to_numeric(df["成交量（股）"], errors="coerce")
        df["成交额（元）"] = pd.to_numeric(df["成交额（元）"], errors="coerce")
        df["日期"] = pd.to_datetime(df["日期"])

        df["代码"] = name
        df["名称"] = name if is_index else ""
        df["所属行业"] = "指数" if is_index else ""
        df["是否ST"] = False
        for c in ["总股本（股）", "流通股本（股）", "总市值（元）", "流通市值（元）",
                   "静态市盈率", "市净率", "静态市销率"]:
            df[c] = np.nan
        df["上市时间"] = ""
        df["退市时间"] = "-"
        df["是否融资融券"] = False
        df = compute_derived(df)
        return df[COLUMNS] if all(c in df.columns for c in COLUMNS) else None
    except Exception:
        return None


def merge_and_save(csv_path, df_new):
    """Prepend new data, merge with existing post-2018 data, save."""
    if csv_path.exists():
        try:
            existing = pd.read_csv(csv_path, encoding="utf-8-sig")
            existing["日期"] = pd.to_datetime(existing["日期"])
            existing = existing[existing["日期"] >= "2018-01-01"]
            combined = pd.concat([df_new, existing], ignore_index=True)
        except Exception:
            combined = df_new
    else:
        combined = df_new
    combined = combined.sort_values("日期").drop_duplicates("日期")
    tmp = csv_path.with_suffix(".tmp")
    combined.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(csv_path)
    return len(combined)


def worker(stock_list, worker_id, result_queue, checkpoint):
    """Download a list of stocks with retry and checkpoint."""
    import baostock as bs
    lg = bs.login()
    print(f"[W{worker_id}] Login OK, {len(stock_list)} stocks assigned", flush=True)

    results = {"ok": 0, "fail": [], "skip": 0}
    t0 = time.time()

    for i, item in enumerate(stock_list):
        sym, code_bs = item["sym"], item["code_bs"]

        # Check checkpoint + existing data
        if sym in checkpoint or already_done(sym):
            results["skip"] += 1
            continue

        # Download with retry
        df = None
        for attempt in range(3):
            df = download_one(bs, code_bs, sym, START_DATE, END_DATE)
            if df is not None and len(df) > 0:
                break
            time.sleep(1)

        if df is None or len(df) == 0:
            results["fail"].append(sym)
        else:
            merge_and_save(STOCK_DIR / f"{sym}.csv", df)
            results["ok"] += 1
            # Update checkpoint atomically
            try:
                current = load_checkpoint()
                current.add(sym)
                save_checkpoint(current)
            except Exception:
                pass

        # Progress every 30 stocks
        if (i + 1) % 30 == 0:
            elapsed = time.time() - t0
            done = results["ok"] + results["skip"]
            rate = done / elapsed if elapsed > 0 else 0
            remaining = len(stock_list) - i - 1
            eta = remaining / rate if rate > 0 else 0
            print(f"[W{worker_id}] {i+1}/{len(stock_list)} "
                  f"ok={results['ok']} skip={results['skip']} fail={len(results['fail'])} "
                  f"ETA={eta/60:.0f}m", flush=True)

    bs.logout()
    elapsed = time.time() - t0
    result_queue.put(results)
    print(f"[W{worker_id}] DONE: {results['ok']} ok, {results['skip']} skip, "
          f"{len(results['fail'])} fail, {elapsed/60:.1f}min", flush=True)


def main():
    t_total = time.time()
    print("=" * 60)
    print("  Baostock 2012-2017 Extension (resume-safe)")
    print("=" * 60)

    # ── Build stock list ──
    from data.config import HS300, CSI1000, CYB_STAR_50, DISABLE_STOCK
    universe = sorted(set(HS300 + CSI1000 + CYB_STAR_50) - DISABLE_STOCK)

    stock_items = []
    for sym in universe:
        code_bs = f"sh.{sym}" if sym.startswith("6") else f"sz.{sym}"
        stock_items.append({"sym": sym, "code_bs": code_bs})

    # Load checkpoint (resume)
    checkpoint = load_checkpoint()
    print(f"Checkpoint: {len(checkpoint)} already done")

    # Also mark stocks that already have data as done
    already = {s for s in universe if already_done(s)}
    checkpoint = checkpoint | already
    if already - checkpoint:
        save_checkpoint(checkpoint)
    print(f"Total done (checkpoint + existing data): {len(checkpoint)}")

    # Filter: only stocks that still need work
    todo = [item for item in stock_items if item["sym"] not in checkpoint]
    print(f"Remaining: {len(todo)} stocks")

    if not todo:
        print("Nothing to do! All stocks already complete.")
        return

    # Split into 2 halves
    mid = len(todo) // 2 + 1
    batch1 = todo[:mid]
    batch2 = todo[mid:]
    print(f"Worker 1: {len(batch1)}, Worker 2: {len(batch2)}")

    # ── Step 1: Indices (single process, respects checkpoint) ──
    print("\n--- Indices ---")
    import baostock as bs
    bs.login()
    for bs_code, name in INDICES.items():
        if name in checkpoint or already_done(name):
            print(f"  {name}: already done, skip")
            continue

        df = None
        for attempt in range(3):
            df = download_one(bs, bs_code, name, START_DATE, END_DATE, is_index=True)
            if df is not None and len(df) > 0:
                break
            time.sleep(1)

        if df is not None and len(df) > 0:
            n = merge_and_save(STOCK_DIR / f"{name}.csv", df)
            checkpoint.add(name)
            save_checkpoint(checkpoint)
            print(f"  {name}: {len(df)} rows -> {n} total")
        else:
            print(f"  {name}: FAILED")
    bs.logout()

    if not batch1 and not batch2:
        print("All done!")
        return

    # ── Step 2: Parallel workers ──
    print(f"\n--- Stocks: {len(todo)} remaining, 2 workers ---")
    print(f"Start: {time.strftime('%H:%M:%S')}")
    q1, q2 = Queue(), Queue()
    p1 = Process(target=worker, args=(batch1, 1, q1, checkpoint))
    p2 = Process(target=worker, args=(batch2, 2, q2, checkpoint))
    p1.start()
    p2.start()

    # Handle Ctrl+C gracefully
    def on_sigint(sig, frame):
        print("\nInterrupted! Progress saved to checkpoint. Resume by re-running.")
        p1.terminate()
        p2.terminate()
        sys.exit(0)
    signal.signal(signal.SIGINT, on_sigint)

    p1.join()
    p2.join()

    r1 = q1.get() if not q1.empty() else {"ok": 0, "fail": [], "skip": 0}
    r2 = q2.get() if not q2.empty() else {"ok": 0, "fail": [], "skip": 0}

    total_ok = r1.get("ok", 0) + r2.get("ok", 0)
    total_fail = r1.get("fail", []) + r2.get("fail", [])
    total_skip = r1.get("skip", 0) + r2.get("skip", 0)

    # ── Step 3: Orchestrator retry of failed stocks ──
    if total_fail:
        print(f"\n--- Orchestrator retry: {len(total_fail)} failed stocks ---")
        bs.login()
        retry_ok = 0
        for sym in total_fail:
            code_bs = f"sh.{sym}" if sym.startswith("6") else f"sz.{sym}"
            df = None
            for attempt in range(3):
                df = download_one(bs, code_bs, sym, START_DATE, END_DATE)
                if df is not None and len(df) > 0:
                    break
                time.sleep(2)
            if df is not None and len(df) > 0:
                merge_and_save(STOCK_DIR / f"{sym}.csv", df)
                checkpoint.add(sym)
                save_checkpoint(checkpoint)
                retry_ok += 1
            else:
                print(f"  {sym}: FAILED permanently")
        bs.logout()
        total_ok += retry_ok
        total_fail = [s for s in total_fail if s not in checkpoint]
        print(f"  Recovered: {retry_ok}, still failed: {len(total_fail)}")

    # ── Step 4: Generate by-day CSVs ──
    print(f"\n--- Generating by-day CSVs for 2012-2017 ---")
    t0 = time.time()
    for year in range(2012, 2018):
        (DAY_DIR / str(year)).mkdir(parents=True, exist_ok=True)

    all_dfs = []
    for csv_file in sorted(STOCK_DIR.glob("*.csv")):
        if csv_file.name.startswith("_"):
            continue
        try:
            df = pd.read_csv(csv_file, encoding="utf-8-sig")
            df["日期"] = pd.to_datetime(df["日期"])
            df_pre = df[(df["日期"] >= START_DATE) & (df["日期"] <= END_DATE)]
            if len(df_pre) > 0:
                all_dfs.append(df_pre)
        except Exception:
            continue

    if all_dfs:
        big = pd.concat(all_dfs, ignore_index=True)
        big["ds"] = big["日期"].dt.strftime("%Y-%m-%d")
        for ds, grp in big.groupby("ds"):
            dt = pd.Timestamp(ds)
            grp.drop(columns=["ds"]).to_csv(
                DAY_DIR / str(dt.year) / f"{ds}.csv",
                index=False, encoding="utf-8-sig",
            )
        n_days = big["ds"].nunique()
        print(f"  {n_days} daily files, {len(big)} rows, {time.time()-t0:.0f}s")

    # ── Summary ──
    final_done = len(load_checkpoint())
    print(f"\n{'='*60}")
    print(f"  Done: {final_done} stocks processed")
    print(f"  New this run: {total_ok}  Failed: {len(total_fail)}")
    print(f"  Total time: {(time.time()-t_total)/60:.1f} min")
    if total_fail:
        print(f"  Failed: {total_fail}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
