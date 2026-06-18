"""指标基类与工具"""
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd


class BaseIndicator(ABC):
    """技术指标抽象基类"""

    @abstractmethod
    def calc(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

    def validate(self, df: pd.DataFrame) -> bool:
        required = ["open", "high", "low", "close", "volume"]
        return all(c in df.columns for c in required)


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder 平滑（用于 ADX、ATR）"""
    return series.ewm(alpha=1/period, adjust=False).mean()


def safe_divide(a, b, default: float = 0.0):
    """安全除法（避免除零）"""
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan).fillna(default)
    return a / b if b != 0 else default
