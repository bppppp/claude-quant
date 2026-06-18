"""数据加载器（金玥数据）"""
from pathlib import Path
from typing import Optional
import pandas as pd

from .cleaner import clean_dataframe
from .column_mapper import standardize_columns


def load_daily_cross_section(date: str, data_dir: str = "data/data-by-day") -> pd.DataFrame:
    """加载单日全市场横截面数据"""
    year = date[:4]
    csv_path = Path(data_dir) / year / f"{date}_金玥数据.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Data not found: {csv_path}")

    df = pd.read_csv(csv_path, dtype={"代码": str, "名称": str})
    df = clean_dataframe(df)
    df = standardize_columns(df)
    return df.reset_index(drop=True)


def load_stock_series(symbol: str,
                       data_dir: str = "data/data-by-stock",
                       start: Optional[str] = None,
                       end: Optional[str] = None) -> pd.DataFrame:
    """加载单只股票时间序列"""
    csv_path = Path(data_dir) / f"{symbol}_金玥数据.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Stock data not found: {csv_path}")

    df = pd.read_csv(csv_path, dtype={"代码": str, "名称": str})
    df = clean_dataframe(df)
    df = standardize_columns(df)

    if start:
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        if "date" not in df.columns:
            df["date"] = pd.to_datetime(df["date"]) if "date" in df.columns else pd.to_datetime(df["日期"])
        df = df[df["date"] <= pd.Timestamp(end)]

    return df.reset_index(drop=True)


def load_stock_cross_section(symbol: str, dates, data_dir: str = "data/data-by-day") -> pd.DataFrame:
    """加载单只股票在多个日期的横截面数据"""
    dfs = []
    for date in dates:
        try:
            df_daily = load_daily_cross_section(date, data_dir)
            df_stock = df_daily[df_daily["code"] == symbol]
            if not df_stock.empty:
                dfs.append(df_stock)
        except FileNotFoundError:
            continue
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)
