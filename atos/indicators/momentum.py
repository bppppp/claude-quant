"""动量类指标：KDJ、RSI、CCI"""
import numpy as np
import pandas as pd


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series,
             n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ 指标"""
    low_n = low.rolling(n, min_periods=n).min()
    high_n = high.rolling(n, min_periods=n).max()
    rsv = (close - low_n) / (high_n - low_n + 1e-9) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"K": k, "D": d, "J": j})


def kdj_golden_cross(kdj_df: pd.DataFrame) -> pd.Series:
    k = kdj_df["K"]
    d = kdj_df["D"]
    return ((k > d) & (k.shift(1) <= d.shift(1))).astype(int)


def kdj_death_cross(kdj_df: pd.DataFrame) -> pd.Series:
    k = kdj_df["K"]
    d = kdj_df["D"]
    return ((k < d) & (k.shift(1) >= d.shift(1))).astype(int)


def calc_rsi(close: pd.Series, periods=(6, 12, 14, 24)) -> pd.DataFrame:
    """RSI 指标"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    result = {}
    for p in periods:
        avg_gain = gain.ewm(alpha=1/p, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/p, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - 100 / (1 + rs)
        result[f"RSI{p}"] = rsi
    return pd.DataFrame(result)


def rsi_overbought(rsi: pd.Series, threshold: float = 70) -> pd.Series:
    return (rsi > threshold).astype(int)


def rsi_oversold(rsi: pd.Series, threshold: float = 30) -> pd.Series:
    return (rsi < threshold).astype(int)


def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """CCI 顺势指标"""
    tp = (high + low + close) / 3
    ma = tp.rolling(period, min_periods=1).mean()
    md = tp.rolling(period, min_periods=1).apply(
        lambda x: np.mean(np.abs(x - x.mean())), raw=True
    )
    cci = (tp - ma) / (0.015 * md + 1e-9)
    return cci
