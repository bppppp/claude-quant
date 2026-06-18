"""通道类指标：布林、ATR、Donchian"""
import numpy as np
import pandas as pd

from .base import wilder_smooth


def calc_boll(close: pd.Series,
              period: int = 20,
              k: float = 2.0) -> pd.DataFrame:
    """布林带"""
    mid = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std()
    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower) / (mid + 1e-9)
    percent_b = (close - lower) / (upper - lower + 1e-9)
    return pd.DataFrame({
        "BOLL_MID": mid,
        "BOLL_UP": upper,
        "BOLL_DOWN": lower,
        "BOLL_WIDTH": width,
        "BOLL_PB": percent_b
    })


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """ATR 真实波幅"""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return wilder_smooth(tr, period)


def calc_donchian(high: pd.Series, low: pd.Series,
                  period: int = 20) -> pd.DataFrame:
    """Donchian 通道"""
    upper = high.rolling(period, min_periods=1).max()
    lower = low.rolling(period, min_periods=1).min()
    mid = (upper + lower) / 2
    return pd.DataFrame({"DC_UP": upper, "DC_LOW": lower, "DC_MID": mid})
