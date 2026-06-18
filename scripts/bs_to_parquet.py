#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convert baostock CSVs (data-by-stock-bs/) → processed parquet (data/processed/v1/).
- Maps Chinese column names → English
- Runs calc_all_indicators for full indicator set
- Merges 2012-2017 bs data with existing 2018+ parquet data
- Preserves existing data where bs doesn't have it
"""
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BS_DIR = PROJECT_ROOT / "data" / "data-by-stock-bs"
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "v1"

# Chinese → English column mapping
COL_MAP = {
    "日期": "date",
    "代码": "code",
    "名称": "name",
    "所属行业": "industry",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "前收盘价": "prev_close",
    "成交量（股）": "volume",
    "成交额（元）": "amount",
    "换手率": "turnover",
    "涨幅%": "pct_change",
    "振幅%": "amplitude",
    "是否ST": "is_st",
    "量比": "vol_ratio",
    "3日涨幅%": "pct_change_3d",
    "6日涨幅%": "pct_change_6d",
    "10日涨幅%": "pct_change_10d",
    "25日涨幅%": "pct_change_25d",
    "是否涨停": "is_limit_up",
    "总股本（股）": "total_shares",
    "流通股本（股）": "float_shares",
    "总市值（元）": "mkt_cap_total",
    "流通市值（元）": "mkt_cap_float",
    "静态市盈率": "pe_ttm",
    "市净率": "pb",
    "静态市销率": "ps_ttm",
    "5日均线": "MA5",
    "10日均线": "MA10",
    "20日均线": "MA20",
    "30日均线": "MA30",
    "60日均线": "MA60",
    "120日均线": "MA120",
    "250日均线": "MA250",
    "上市时间": "list_date",
    "退市时间": "delist_date",
    "是否融资融券": "is_margin",
}


def convert_one(sym):
    """Convert one stock: bs CSV → processed parquet."""
    bs_path = BS_DIR / f"{sym}.csv"
    proc_path = PROC_DIR / "stock" / f"{sym}.parquet"

    if not bs_path.exists():
        return None

    # Read bs CSV
    df_bs = pd.read_csv(bs_path, encoding="utf-8-sig")

    # Map columns
    df_en = pd.DataFrame()
    for chn, eng in COL_MAP.items():
        if chn in df_bs.columns:
            df_en[eng] = df_bs[chn]

    df_en["date"] = pd.to_datetime(df_en["date"])

    # Keep only 2012-2017 from bs (2018+ comes from existing parquet)
    df_bs_pre = df_en[df_en["date"] < "2018-01-01"].copy()

    if len(df_bs_pre) == 0:
        return None  # Stock IPO'd after 2018, nothing to add

    # Read existing parquet (2018+ data with full indicators)
    if proc_path.exists():
        df_proc = pd.read_parquet(proc_path)
        if "date" in df_proc.columns:
            df_proc["date"] = pd.to_datetime(df_proc["date"])
        # Keep only post-2017 from processed
        df_proc = df_proc[df_proc["date"] >= "2018-01-01"].copy()
    else:
        df_proc = pd.DataFrame()

    # For the bs pre-2018 data, compute full indicators
    # First, ensure all required OHLCV columns exist
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df_bs_pre.columns:
            df_bs_pre[col] = np.nan

    # Run calc_all_indicators on bs_pre data
    try:
        from atos.indicators.pipeline import calc_all_indicators
        # Need to ensure minimum columns for calc_all_indicators
        df_bs_pre_idx = df_bs_pre.set_index("date")
        # Fill missing required columns
        for col in ["MA20", "MA60", "MA120"]:
            if col not in df_bs_pre_idx.columns:
                df_bs_pre_idx[col] = df_bs_pre_idx["close"].rolling(
                    int(col.replace("MA", ""))
                ).mean()
        df_with_indicators = calc_all_indicators(df_bs_pre_idx)
        # Merge back: keep bs columns + add computed indicators
        # calc_all_indicators returns a DataFrame with all 60+ columns
        df_result = df_with_indicators.reset_index()
    except Exception as e:
        # Fallback: just use the bs columns as-is
        df_result = df_bs_pre
        print(f"  Warning {sym}: indicator calc failed ({e}), using basic columns")

    # Merge with existing processed data
    if len(df_proc) > 0:
        # Align columns
        for col in df_result.columns:
            if col not in df_proc.columns:
                df_proc[col] = np.nan
        for col in df_proc.columns:
            if col not in df_result.columns:
                df_result[col] = np.nan
        combined = pd.concat([df_result, df_proc[df_result.columns]], ignore_index=True)
    else:
        combined = df_result

    combined = combined.sort_values("date").drop_duplicates("date")
    combined["date"] = pd.to_datetime(combined["date"])

    # Save
    proc_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(proc_path, compression="snappy", index=False)
    return len(combined)


def main():
    t0 = time.time()
    print("Converting baostock CSVs → processed parquet (2012-2017 prepend)...")

    # Get all bs CSV files
    bs_files = sorted(
        f.stem for f in BS_DIR.glob("*.csv")
        if not f.name.startswith("_")
        and f.stem not in ("hs300", "csi1000", "sse50")
    )

    print(f"BS stock files: {len(bs_files)}")

    n_new, n_skip, n_fail = 0, 0, 0
    for i, sym in enumerate(bs_files):
        try:
            result = convert_one(sym)
            if result is None:
                n_skip += 1
            else:
                n_new += 1
        except Exception as e:
            n_fail += 1
            if n_fail <= 10:
                print(f"  Error {sym}: {e}")

        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(bs_files)} new={n_new} skip={n_skip} fail={n_fail}")

    # ── Convert indices ──
    print("\nConverting indices...")
    for name in ["hs300", "csi1000", "sse50"]:
        bs_path = BS_DIR / f"{name}.csv"
        if not bs_path.exists():
            print(f"  {name}: bs CSV not found")
            continue

        df = pd.read_csv(bs_path, encoding="utf-8-sig")
        df_en = pd.DataFrame()
        for chn, eng in COL_MAP.items():
            if chn in df.columns:
                df_en[eng] = df[chn]
        df_en["date"] = pd.to_datetime(df_en["date"])

        # Save as market parquet
        out_path = PROC_DIR / "market" / f"{name}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df_en.to_parquet(out_path, compression="snappy", index=False)
        print(f"  {name}: {len(df_en)} rows -> {out_path}")

    # ── Summary ──
    print(f"\nDone: {n_new} extended, {n_skip} skipped (post-2017 IPO), "
          f"{n_fail} failed")
    print(f"Time: {(time.time()-t0)/60:.1f} min")

    # Verify a few
    for sym in ["000001", "600519", "300750"]:
        p = PROC_DIR / "stock" / f"{sym}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "date" in df.columns:
                dr = pd.to_datetime(df["date"])
                print(f"  {sym}: {dr.min().date()} -> {dr.max().date()} ({len(df)} rows)")


if __name__ == "__main__":
    main()
