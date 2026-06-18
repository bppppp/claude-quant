#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extend v2 processed parquet with 2012-2017 data from baostock CSVs.

- Extracts 2012-2017 from bs CSVs
- Maps Chinese→English, computes indicators via calc_all_indicators
- Prepends to existing v2 parquet (keeps 2018+ intact)
"""
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BS_DIR = PROJECT_ROOT / "data" / "data-by-stock-bs"
V2_DIR = PROJECT_ROOT / "data" / "processed" / "v2"

COL_MAP = {
    "日期": "date", "代码": "code", "名称": "name", "所属行业": "industry",
    "开盘价": "open", "最高价": "high", "最低价": "low", "收盘价": "close",
    "前收盘价": "prev_close",
    "成交量（股）": "volume", "成交额（元）": "amount",
    "换手率": "turnover", "涨幅%": "pct_change", "振幅%": "amplitude",
    "是否ST": "is_st", "量比": "vol_ratio",
    "3日涨幅%": "pct_change_3d", "6日涨幅%": "pct_change_6d",
    "10日涨幅%": "pct_change_10d", "25日涨幅%": "pct_change_25d",
    "是否涨停": "is_limit_up",
    "总股本（股）": "total_shares", "流通股本（股）": "float_shares",
    "总市值（元）": "mkt_cap_total", "流通市值（元）": "mkt_cap_float",
    "静态市盈率": "pe_ttm", "市净率": "pb", "静态市销率": "ps_ttm",
    "5日均线": "MA5", "10日均线": "MA10", "20日均线": "MA20",
    "30日均线": "MA30", "60日均线": "MA60",
    "120日均线": "MA120", "250日均线": "MA250",
    "上市时间": "list_date", "退市时间": "delist_date", "是否融资融券": "is_margin",
}

# Columns required by backtest engine
KEEP_COLS = [
    "open", "high", "low", "close", "prev_close",
    "volume", "amount", "turnover", "pct_change", "amplitude",
    "is_st", "vol_ratio", "pct_change_3d", "pct_change_6d",
    "pct_change_10d", "pct_change_25d", "is_limit_up",
    "total_shares", "float_shares", "mkt_cap_total", "mkt_cap_float",
    "pe_ttm", "pb", "ps_ttm",
    "MA5", "MA10", "MA20", "MA30", "MA60", "MA120", "MA250",
    "list_date", "delist_date", "is_margin",
    # Below computed by calc_all_indicators
    "DIF", "DEA", "MACD", "PDI", "NDI", "DX", "ADX", "ATR",
    "MA_ALIGN", "MA_CONV", "K", "D", "J",
    "RSI6", "RSI12", "RSI14", "RSI24", "CCI",
    "BOLL_MID", "BOLL_UP", "BOLL_DOWN", "BOLL_WIDTH", "BOLL_PB",
    "DC_UP", "DC_LOW", "DC_MID",
    "OBV", "OBV_MA", "VWAP", "VOL_RATIO", "MFI",
]


def process_stock(sym):
    """Extend one stock's v2 parquet with 2012-2017 bs data."""
    bs_path = BS_DIR / f"{sym}.csv"
    v2_path = V2_DIR / "stock" / f"{sym}.parquet"

    if not bs_path.exists():
        return "no_bs"

    # Read bs CSV
    df_bs = pd.read_csv(bs_path, encoding="utf-8-sig")

    # Map to English, extract 2012-2017
    df_en = pd.DataFrame()
    df_en["date"] = pd.to_datetime(df_bs["日期"])
    for chn, eng in COL_MAP.items():
        if chn in df_bs.columns and eng not in df_en.columns:
            df_en[eng] = df_bs[chn]

    df_pre = df_en[(df_en["date"] >= "2012-01-01") & (df_en["date"] < "2018-01-01")].copy()
    if len(df_pre) == 0:
        return "no_pre2018"

    # Ensure OHLCV
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col not in df_pre.columns:
            df_pre[col] = np.nan

    # Compute indicators
    df_pre = df_pre.set_index("date")
    try:
        from atos.indicators.pipeline import calc_all_indicators
        df_pre = calc_all_indicators(df_pre)
    except Exception:
        pass  # use whatever columns we have

    # Read existing v2 parquet
    if v2_path.exists():
        df_v2 = pd.read_parquet(v2_path)
        # Keep only post-2017
        if isinstance(df_v2.index, pd.DatetimeIndex):
            df_v2 = df_v2[df_v2.index >= "2018-01-01"]
        elif "date" in df_v2.columns:
            df_v2["date"] = pd.to_datetime(df_v2["date"])
            df_v2 = df_v2[df_v2["date"] >= "2018-01-01"]
            df_v2 = df_v2.set_index("date")
    else:
        df_v2 = pd.DataFrame()

    # Merge: align columns then concat
    combined = pd.concat([df_pre, df_v2], axis=0)
    combined = combined[~combined.index.duplicated(keep="first")]
    combined = combined.sort_index()

    # Add code/name/industry columns back if missing
    if "code" not in combined.columns and "code" in df_en.columns:
        combined["code"] = df_en["code"].iloc[0] if len(df_en) > 0 else sym
    if "name" not in combined.columns and "name" in df_en.columns:
        combined["name"] = df_en["name"].iloc[0] if len(df_en) > 0 else ""
    if "industry" not in combined.columns and "industry" in df_en.columns:
        combined["industry"] = df_en["industry"].iloc[0] if len(df_en) > 0 else ""

    # Save
    v2_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(v2_path, compression="snappy")
    return len(df_pre)


def process_market(name):
    """Extend market index v2 parquet with 2012-2017 bs data."""
    bs_path = BS_DIR / f"{name}.csv"
    v2_path = V2_DIR / "market" / f"{name}.parquet"

    if not bs_path.exists():
        return "no_bs"

    df_bs = pd.read_csv(bs_path, encoding="utf-8-sig")
    df_en = pd.DataFrame()
    df_en["date"] = pd.to_datetime(df_bs["日期"])
    for chn, eng in COL_MAP.items():
        if chn in df_bs.columns and eng not in df_en.columns:
            df_en[eng] = df_bs[chn]

    df_pre = df_en[(df_en["date"] >= "2012-01-01") & (df_en["date"] < "2018-01-01")].copy()
    if len(df_pre) == 0:
        return "no_pre2018"

    df_pre = df_pre.set_index("date")

    if v2_path.exists():
        df_v2 = pd.read_parquet(v2_path)
        if not isinstance(df_v2.index, pd.DatetimeIndex):
            df_v2["date"] = pd.to_datetime(df_v2["date"])
            df_v2 = df_v2.set_index("date")
        df_v2 = df_v2[df_v2.index >= "2018-01-01"]
    else:
        df_v2 = pd.DataFrame()

    combined = pd.concat([df_pre, df_v2], axis=0)
    combined = combined[~combined.index.duplicated(keep="first")]
    combined = combined.sort_index()

    v2_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(v2_path, compression="snappy")
    return len(df_pre)


def main():
    t0 = time.time()
    print("Extending v2 parquet with baostock 2012-2017 data...")

    # ── Market indices ──
    print("\n--- Indices ---")
    for name in ["hs300", "csi1000", "sse50"]:
        result = process_market(name)
        print(f"  {name}: {result}")

    # ── Stocks ──
    print("\n--- Stocks ---")
    bs_files = sorted(f.stem for f in BS_DIR.glob("*.csv")
                      if not f.name.startswith("_")
                      and f.stem not in ("hs300", "csi1000", "sse50"))

    n_ext, n_no_bs, n_no_pre = 0, 0, 0
    for i, sym in enumerate(bs_files):
        try:
            result = process_stock(sym)
            if result == "no_bs":
                n_no_bs += 1
            elif result == "no_pre2018":
                n_no_pre += 1
            else:
                n_ext += 1
        except Exception as e:
            print(f"  Error {sym}: {e}")
            n_no_bs += 1

        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(bs_files)}  ext={n_ext} no_pre={n_no_pre} no_bs={n_no_bs}")

    # ── Verify ──
    print(f"\n--- Verification ---")
    for name in ["hs300", "csi1000"]:
        p = V2_DIR / "market" / f"{name}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            idx = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df["date"])
            print(f"  {name}: {idx.min().date()} → {idx.max().date()} ({len(df)} rows)")

    for sym in ["000001", "603300"]:
        p = V2_DIR / "stock" / f"{sym}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            idx = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df["date"])
            pre = (idx >= "2012-01-01") & (idx < "2018-01-01")
            print(f"  {sym}: {idx.min().date()} → {idx.max().date()} "
                  f"({pre.sum()} pre-2018, {len(df)} total)")

    print(f"\nDone: {n_ext} extended, {n_no_pre} no pre-2018 data, "
          f"{n_no_bs} no bs CSV. Time: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
