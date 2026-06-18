"""量价类指标：OBV、VWAP、MFI、量比"""
import numpy as np
import pandas as pd


def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """OBV 能量潮"""
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def calc_vwap(high: pd.Series, low: pd.Series, close: pd.Series,
              volume: pd.Series, period: int = 20) -> pd.Series:
    """VWAP 成交量加权均价（滚动）"""
    tp = (high + low + close) / 3
    vwap = (tp * volume).rolling(period, min_periods=1).sum() / \
           (volume.rolling(period, min_periods=1).sum() + 1e-9)
    return vwap


def calc_volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """量比：今日成交量 / 过去 N 日均量"""
    return volume / volume.rolling(period, min_periods=1).mean()


def calc_mfi(high: pd.Series, low: pd.Series, close: pd.Series,
             volume: pd.Series, period: int = 14) -> pd.Series:
    """MFI 资金流量指标"""
    tp = (high + low + close) / 3
    rmf = tp * volume
    positive = pd.Series(0.0, index=close.index)
    negative = pd.Series(0.0, index=close.index)
    positive[tp > tp.shift(1)] = rmf[tp > tp.shift(1)]
    negative[tp < tp.shift(1)] = rmf[tp < tp.shift(1)]
    pmf = positive.rolling(period, min_periods=1).sum()
    nmf = negative.rolling(period, min_periods=1).sum()
    mfr = pmf / (nmf + 1e-9)
    mfi = 100 - 100 / (1 + mfr)
    return mfi
