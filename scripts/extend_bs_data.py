#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extend baostock data back to 2012-01-01.

1. Downloads index data (hs300, csi1000, sse50) 2012-2017
2. Downloads stock OHLCV 2012-2017 for pre-2018 stocks
3. Prepends to existing by-stock CSVs
4. Generates by-day CSVs for 2012-2017
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Config ──
START_DATE = "2012-01-01"
END_DATE = "2017-12-31"
STOCK_DIR = PROJECT_ROOT / "data" / "data-by-stock-bs"
DAY_DIR = PROJECT_ROOT / "data" / "data-by-day-bs"

# Index mapping: baostock code -> output filename
INDICES = {
    "sh.000300": "hs300",
    "sh.000852": "csi1000",
    "sh.000016": "sse50",
}

# Column names (matching existing bs format)
COLUMNS = [
    "日期", "代码", "名称", "所属行业", "开盘价", "最高价", "最低价", "收盘价",
    "前收盘价", "成交量（股）", "成交额（元）", "换手率", "涨幅%", "振幅%",
    "是否ST", "量比", "3日涨幅%", "6日涨幅%", "10日涨幅%", "25日涨幅%",
    "是否涨停", "总股本（股）", "流通股本（股）", "总市值（元）", "流通市值（元）",
    "静态市盈率", "市净率", "静态市销率", "5日均线", "10日均线", "20日均线",
    "30日均线", "60日均线", "120日均线", "250日均线", "上市时间", "退市时间",
    "是否融资融券",
]


def compute_derived_columns(df):
    """Compute all 38 derived columns from raw OHLCV data."""
    close = df["收盘价"]
    high = df["最高价"]
    low = df["最低价"]
    volume = df["成交量（股）"]

    # prev_close
    df["前收盘价"] = close.shift(1)

    # pct_change
    df["涨幅%"] = (close / df["前收盘价"] - 1) * 100

    # amplitude
    df["振幅%"] = (high - low) / df["前收盘价"] * 100

    # turnover (needs float_shares, fill NaN)
    if "换手率" not in df.columns or df["换手率"].isna().all():
        df["换手率"] = np.nan

    # multi-day returns
    for period, col in [(3, "3日涨幅%"), (6, "6日涨幅%"),
                         (10, "10日涨幅%"), (25, "25日涨幅%")]:
        df[col] = (close / close.shift(period) - 1) * 100

    # volume ratio (need 5-day avg volume, fill NaN for first rows)
    df["量比"] = volume / volume.rolling(5).mean()

    # limit up (approximate: 9.5% for normal stocks)
    df["是否涨停"] = df["涨幅%"] >= 9.5

    # MA lines
    for period, col in [(5, "5日均线"), (10, "10日均线"), (20, "20日均线"),
                         (30, "30日均线"), (60, "60日均线"),
                         (120, "120日均线"), (250, "250日均线")]:
        df[col] = close.rolling(period).mean()

    return df


def download_stock(bs, code_bs, code6):
    """Download single stock from baostock, return DataFrame or None."""
    try:
        rs = bs.query_history_k_data_plus(
            code_bs,
            "date,code,open,high,low,close,volume,amount",
            start_date=START_DATE, end_date=END_DATE,
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
                                          "最低价", "收盘价", "成交量（股）",
                                          "成交额（元）"])
        # Convert types
        for col in ["开盘价", "最高价", "最低价", "收盘价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["成交量（股）"] = pd.to_numeric(df["成交量（股）"], errors="coerce")
        df["成交额（元）"] = pd.to_numeric(df["成交额（元）"], errors="coerce")
        df["日期"] = pd.to_datetime(df["日期"])

        # Fill static columns
        df["代码"] = code6
        df["名称"] = ""
        df["所属行业"] = ""
        df["是否ST"] = False
        df["总股本（股）"] = np.nan
        df["流通股本（股）"] = np.nan
        df["总市值（元）"] = np.nan
        df["流通市值（元）"] = np.nan
        df["静态市盈率"] = np.nan
        df["市净率"] = np.nan
        df["静态市销率"] = np.nan
        df["上市时间"] = ""
        df["退市时间"] = "-"
        df["是否融资融券"] = False

        # Compute derived columns
        df = compute_derived_columns(df)

        return df[COLUMNS] if all(c in df.columns for c in COLUMNS) else None
    except Exception as e:
        print(f"  Error {code_bs}: {e}")
        return None


def download_index(bs, code_bs, name):
    """Download index data, return DataFrame with stock-like columns."""
    try:
        rs = bs.query_history_k_data_plus(
            code_bs,
            "date,code,open,high,low,close,volume,amount",
            start_date=START_DATE, end_date=END_DATE,
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
                                          "最低价", "收盘价", "成交量（股）",
                                          "成交额（元）"])
        for col in ["开盘价", "最高价", "最低价", "收盘价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["成交量（股）"] = pd.to_numeric(df["成交量（股）"], errors="coerce")
        df["成交额（元）"] = pd.to_numeric(df["成交额（元）"], errors="coerce")
        df["日期"] = pd.to_datetime(df["日期"])

        df["代码"] = name
        df["名称"] = name
        df["所属行业"] = "指数"
        df["是否ST"] = False
        for c in ["总股本（股）", "流通股本（股）", "总市值（元）", "流通市值（元）",
                   "静态市盈率", "市净率", "静态市销率", "换手率"]:
            df[c] = np.nan
        df["上市时间"] = ""
        df["退市时间"] = "-"
        df["是否融资融券"] = False

        df = compute_derived_columns(df)
        return df[COLUMNS] if all(c in df.columns for c in COLUMNS) else None
    except Exception as e:
        print(f"  Error index {code_bs}: {e}")
        return None


def main():
    import baostock as bs

    t_total = time.time()

    # ── 1. Login ──
    print("=" * 60)
    print("  Baostock Data Extension: 2012-01-01 -> 2017-12-31")
    print("=" * 60)
    lg = bs.login()
    print(f"Login: {lg.error_code} {lg.error_msg}")

    # ── 2. Download indices ──
    print("\n[1/3] Downloading indices...")
    for bs_code, name in INDICES.items():
        t0 = time.time()
        df = download_index(bs, bs_code, name)
        if df is not None:
            out_path = STOCK_DIR / f"{name}.csv"
            # Check if existing file has data before 2018
            if out_path.exists():
                existing = pd.read_csv(out_path, encoding="utf-8-sig")
                existing["日期"] = pd.to_datetime(existing["日期"])
                existing = existing[existing["日期"] < "2018-01-01"]
                if len(existing) > 0:
                    # Already has pre-2018 data, skip
                    print(f"  {name}: already has {len(existing)} pre-2018 rows, skip")
                    continue
                # Merge
                combined = pd.concat([df, existing], ignore_index=True)
            else:
                combined = df
            combined = combined.sort_values("日期").drop_duplicates("日期")
            combined.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"  {name}: {len(df)} rows in {time.time()-t0:.1f}s -> {out_path}")
        else:
            print(f"  {name}: FAILED")

    # ── 3. Download stocks ──
    print("\n[2/3] Downloading stock data...")
    # Get stock list from existing bs files
    from data.config import HS300, CSI1000, CYB_STAR_50, DISABLE_STOCK
    universe = sorted(set(HS300 + CSI1000 + CYB_STAR_50) - DISABLE_STOCK)

    # Build baostock code mapping
    bs_code_map = {}
    for sym in universe:
        if sym.startswith("6") or sym.startswith("68"):
            bs_code_map[sym] = f"sh.{sym}"
        else:
            bs_code_map[sym] = f"sz.{sym}"

    # Filter: only stocks with existing bs files AND that need 2012-2017
    to_download = []
    for sym in universe:
        csv_path = STOCK_DIR / f"{sym}.csv"
        if not csv_path.exists():
            continue  # no existing bs data for this stock
        # Check if already has pre-2018 data
        try:
            existing = pd.read_csv(csv_path, encoding="utf-8-sig")
            existing["日期"] = pd.to_datetime(existing["日期"])
            pre_count = (existing["日期"] < "2018-01-01").sum()
            if pre_count > 100:  # already has >100 pre-2018 rows
                continue
        except Exception:
            pass
        to_download.append(sym)

    # Also find stocks that IPO'd before 2018 but have NO bs file
    for sym in universe:
        csv_path = STOCK_DIR / f"{sym}.csv"
        if csv_path.exists():
            continue
        # Check if this stock existed before 2018 (from processed data)
        proc_path = PROJECT_ROOT / "data" / "processed" / "v1" / "stock" / f"{sym}.parquet"
        if proc_path.exists():
            try:
                df = pd.read_parquet(proc_path)
                if "date" in df.columns:
                    dmin = pd.to_datetime(df["date"]).min()
                    if dmin < pd.Timestamp("2018-01-01"):
                        to_download.append(sym)
            except Exception:
                pass

    to_download = sorted(set(to_download))
    print(f"  Stocks to process: {len(to_download)}")
    print(f"  ({sum(1 for s in to_download if (STOCK_DIR/f'{s}.csv').exists())} existing, "
          f"{sum(1 for s in to_download if not (STOCK_DIR/f'{s}.csv').exists())} new)")

    n_ok, n_fail, n_skip = 0, 0, 0
    t_batch = time.time()
    for i, sym in enumerate(to_download):
        code_bs = bs_code_map.get(sym)
        if not code_bs:
            n_skip += 1
            continue

        t0 = time.time()
        csv_path = STOCK_DIR / f"{sym}.csv"
        df_new = download_stock(bs, code_bs, sym)

        if df_new is None or len(df_new) == 0:
            n_fail += 1
            # If no data but stock existed pre-2018, it might have delisted
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(to_download)}] {sym}: no data (delisted?)")
            continue

        # Merge with existing if file exists
        if csv_path.exists():
            try:
                existing = pd.read_csv(csv_path, encoding="utf-8-sig")
                existing["日期"] = pd.to_datetime(existing["日期"])
                # Remove pre-2018 rows from existing (we're replacing them)
                existing = existing[existing["日期"] >= "2018-01-01"]
                combined = pd.concat([df_new, existing], ignore_index=True)
            except Exception:
                combined = df_new
        else:
            combined = df_new

        combined = combined.sort_values("日期").drop_duplicates("日期")
        combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
        n_ok += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - t_batch
            eta = elapsed / (i + 1) * (len(to_download) - i - 1)
            print(f"  [{i+1}/{len(to_download)}] {sym}: {len(df_new)} rows "
                  f"({time.time()-t0:.1f}s) | batch={elapsed:.0f}s ETA={eta/60:.0f}min")

    bs.logout()

    # ── 4. Generate by-day CSVs for 2012-2017 ──
    print(f"\n[3/3] Generating by-day CSVs for 2012-2017...")
    t0 = time.time()
    year_dirs = {}
    for year in range(2012, 2018):
        yd = DAY_DIR / str(year)
        yd.mkdir(parents=True, exist_ok=True)
        year_dirs[year] = yd

    # Read all by-stock files, extract 2012-2017 rows, group by date
    all_pre2018 = []
    for csv_file in sorted(STOCK_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(csv_file, encoding="utf-8-sig")
            df["日期"] = pd.to_datetime(df["日期"])
            df_pre = df[(df["日期"] >= START_DATE) & (df["日期"] <= END_DATE)]
            if len(df_pre) > 0:
                all_pre2018.append(df_pre)
        except Exception:
            continue

    if all_pre2018:
        big = pd.concat(all_pre2018, ignore_index=True)
        big["日期_str"] = big["日期"].dt.strftime("%Y-%m-%d")
        for date_str, group in big.groupby("日期_str"):
            dt = pd.Timestamp(date_str)
            year_dir = year_dirs.get(dt.year)
            if year_dir:
                out = group.drop(columns=["日期_str"])
                out.to_csv(year_dir / f"{date_str}.csv", index=False, encoding="utf-8-sig")
        print(f"  Generated {len(big['日期_str'].unique())} daily files "
              f"({len(big)} rows) in {time.time()-t0:.0f}s")
    else:
        print("  No pre-2018 data found!")

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  Done: {n_ok} OK, {n_fail} failed, {n_skip} skipped")
    print(f"  Total time: {(time.time()-t_total)/60:.1f} min")
    print(f"  Data: {START_DATE} -> {END_DATE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
