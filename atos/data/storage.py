"""Parquet 缓存存储 + 预计算数据加载"""
from pathlib import Path
from typing import Optional
import pandas as pd


class ParquetCache:
    """Parquet 缓存（计算结果）"""

    def __init__(self, base_dir: str = "data/processed"):
        self.base_dir = Path(base_dir)

    def save(self, symbol: str, df: pd.DataFrame, category: str = "stock"):
        path = self.base_dir / category / f"{symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, compression="snappy", index=False)

    def load(self, symbol: str, category: str = "stock") -> pd.DataFrame:
        path = self.base_dir / category / f"{symbol}.parquet"
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def exists(self, symbol: str, category: str = "stock") -> bool:
        return (self.base_dir / category / f"{symbol}.parquet").exists()


def save_optimized(df: pd.DataFrame, path: Path):
    """优化的 Parquet 保存（float64->float32, int64->int32）"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = df[col].astype("float32")
    for col in df.select_dtypes(include=["int64"]).columns:
        if df[col].max() < 2**31:
            df[col] = df[col].astype("int32")
    # 如果索引是 DatetimeIndex，重置为 date 列
    if isinstance(df.index, pd.DatetimeIndex) and "date" not in df.columns:
        df = df.reset_index()
        if "index" in df.columns:
            df = df.rename(columns={"index": "date"})
    df.to_parquet(path, compression="snappy", index=False)


def load_processed(symbol: str,
                    version: str = "v2",
                    start: str = None,
                    end: str = None,
                    cache_dir: str = None) -> Optional[pd.DataFrame]:
    """加载预计算的股票数据（含所有指标 + 状态 + 因子）"""
    if cache_dir is None:
        cache_dir = f"data/processed/{version}"
    path = Path(cache_dir) / "stock" / f"{symbol}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    # 确保索引是 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
        else:
            # 索引是 RangeIndex（Parquet 默认），需从某处获取日期
            # 缓存保存时 date 列包含在数据中
            pass
    # 用列过滤替代索引过滤（如果索引不是 datetime）
    if isinstance(df.index, pd.DatetimeIndex):
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
    return df


def load_processed_benchmark(name: str = "hs300",
                                version: str = "v2",
                                start: str = None,
                                end: str = None,
                                cache_dir: str = None) -> Optional[pd.DataFrame]:
    """加载预计算的大盘指数数据"""
    if cache_dir is None:
        cache_dir = f"data/processed/{version}"
    path = Path(cache_dir) / "market" / f"{name}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
    if isinstance(df.index, pd.DatetimeIndex):
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
    return df
