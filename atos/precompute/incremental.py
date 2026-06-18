"""增量预计算器"""
import time
from pathlib import Path

import pandas as pd

from atos.data.loader import load_stock_series, load_daily_cross_section
from atos.indicators.pipeline import calc_all_indicators
from atos.data.storage import save_optimized


class IncrementalUpdater:
    """增量更新器 - 单只股票的指标预计算"""

    def __init__(self, config=None, cache_dir: str = "data/processed/v1"):
        self.config = config
        self.cache_dir = Path(cache_dir)

    def update_symbol(self, symbol: str, data_dir: str = "data/data-by-stock",
                       force: bool = False) -> dict:
        """增量更新单只股票的所有预计算项

        Returns:
            {
                "incremental": bool,
                "new_rows": int,
                "compute_time": float,
                "cache_path": str,
            }
        """
        start = time.time()
        cache_path = self.cache_dir / "stock" / f"{symbol}.parquet"

        # 1. 加载原始数据
        raw = load_stock_series(symbol, data_dir=data_dir)

        # 2. 检查是否需要增量
        new_data = raw
        if cache_path.exists() and not force:
            try:
                cached = pd.read_parquet(cache_path)
                cached_dates = pd.to_datetime(cached.index) if not isinstance(cached.index, pd.DatetimeIndex) else cached.index
                cached_max = cached_dates.max()
                raw_dates = pd.to_datetime(raw["date"]) if "date" in raw.columns else raw.index
                new_data = raw[raw_dates > cached_max]
            except Exception:
                new_data = raw

        if len(new_data) == 0 and cache_path.exists():
            return {"incremental": False, "new_rows": 0, "compute_time": time.time() - start,
                    "cache_path": str(cache_path)}

        # 3. 计算指标
        result = calc_all_indicators(new_data if len(new_data) < len(raw) else raw)

        # 4. 合并
        if cache_path.exists() and not force and len(new_data) < len(raw):
            cached = pd.read_parquet(cache_path)
            if isinstance(cached.index, pd.DatetimeIndex):
                cached = cached.reset_index()
            combined = pd.concat([cached, result], ignore_index=True)
            if "date" in combined.columns:
                combined = combined.drop_duplicates(subset=["date"], keep="last")
                combined = combined.set_index("date")
        else:
            if "date" in result.columns:
                result["date"] = pd.to_datetime(result["date"])
                result = result.set_index("date")

        # 5. 保存
        save_optimized(result, cache_path)

        return {
            "incremental": True,
            "new_rows": len(new_data),
            "compute_time": time.time() - start,
            "cache_path": str(cache_path),
        }

    def load_processed(self, symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
        """加载预计算的股票数据"""
        cache_path = self.cache_dir / "stock" / f"{symbol}.parquet"
        if not cache_path.exists():
            return None
        df = pd.read_parquet(cache_path)
        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]
        return df
