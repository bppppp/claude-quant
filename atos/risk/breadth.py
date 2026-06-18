"""ATOS2 v2: 真实 market_breadth 计算
用 HS300 全部 300 只成份股中 close > MA60 的比例作为 breadth。
"""
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

from atos.data.universe import get_universe


def compute_hs300_breadth_series(
    start: str = "2018-01-01",
    end: str = "2020-04-30",
    data_dir: str = "data/processed/v1/stock",
) -> pd.Series:
    """计算 HS300 真实 breadth 时间序列

    Returns:
        pd.Series: 索引为日期，值为当日 close > MA60 的 HS300 股票占比 [0, 1]
    """
    cache_path = Path(data_dir)
    if not cache_path.exists():
        return pd.Series(dtype=float)

    hs300 = get_universe("HS300")
    daily_count = []
    daily_dates = None

    for sym in hs300:
        cache_file = cache_path / f"{sym}.parquet"
        if not cache_file.exists():
            continue
        try:
            df = pd.read_parquet(cache_file, columns=["close", "MA60"])
            df = df.loc[start:end]
            above = (df["close"] > df["MA60"]).fillna(False)
            if daily_dates is None:
                daily_dates = above.index
            daily_count.append(above.astype(int).values)
        except Exception:
            continue

    if not daily_count or daily_dates is None:
        return pd.Series(dtype=float)

    # 按日期汇总
    import numpy as np
    arr = np.array(daily_count).T  # (T, N)
    breadth = arr.sum(axis=1) / arr.shape[1]
    return pd.Series(breadth, index=daily_dates)


class RealBreadthCache:
    """缓存 HS300 breadth 序列以加速"""

    _instance: Optional["RealBreadthCache"] = None

    def __init__(self):
        self._cache: Dict[str, pd.Series] = {}

    @classmethod
    def get_instance(cls) -> "RealBreadthCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_breadth(self, start: str, end: str) -> pd.Series:
        key = f"{start}_{end}"
        if key not in self._cache:
            self._cache[key] = compute_hs300_breadth_series(start, end)
        return self._cache[key]

    def get_breadth_on_date(self, date: pd.Timestamp,
                             start: str = "2018-01-01",
                             end: str = "2020-04-30") -> float:
        """获取某日的 breadth（最近有效值）"""
        s = self.get_breadth(start, end)
        if len(s) == 0:
            return 1.0
        # 找 <= date 的最近值
        valid = s.index[s.index <= date]
        if len(valid) == 0:
            return 1.0
        return float(s.loc[valid[-1]])
