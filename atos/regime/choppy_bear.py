"""震荡下行检测 - 4 维向量化"""
import numpy as np
import pandas as pd


def detect_choppy_bear(
    df: pd.DataFrame,
    cum_ret_th: float = -0.05,
    cum_ret_upper: float = -0.20,
    volatility_th: float = 0.18,
    ma60_slope_th: float = 0.00025,
    score_threshold: int = 3,
) -> dict:
    """震荡下行检测（4 维）

    Returns:
        {
            "is_choppy_bear": bool,
            "score": int,
            "conditions": dict,
            "metrics": dict
        }
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    log_ret = np.log(close / close.shift(1))

    cum_ret_60d = close.iloc[-1] / close.iloc[-60] - 1 if len(close) >= 60 else 0
    cond_1 = (cum_ret_60d < cum_ret_th) and (cum_ret_60d > cum_ret_upper)

    vol_60d = log_ret.rolling(60).std().iloc[-1] * np.sqrt(252) if len(close) >= 60 else 1.0
    cond_2 = vol_60d < volatility_th

    if len(ma60) >= 21:
        ma60_20d_ago = ma60.iloc[-21]
    else:
        ma60_20d_ago = ma60.iloc[0]
    ma60_slope = (ma60.iloc[-1] - ma60_20d_ago) / (ma60_20d_ago + 1e-9)
    cond_3 = abs(ma60_slope) < ma60_slope_th

    cond_4 = ma20.iloc[-1] < ma60.iloc[-1]

    conditions = {
        "cum_ret_60d_negative": cond_1,
        "low_volatility": cond_2,
        "ma60_flat_or_down": cond_3,
        "ma20_below_ma60": cond_4,
    }

    score = sum(int(v) for v in conditions.values())
    is_choppy_bear = score >= score_threshold

    return {
        "is_choppy_bear": is_choppy_bear,
        "score": score,
        "conditions": conditions,
        "metrics": {
            "cum_ret_60d": cum_ret_60d,
            "vol_60d": vol_60d,
            "ma60_slope": ma60_slope,
            "ma20_vs_ma60": (ma20.iloc[-1] / ma60.iloc[-1] - 1) if ma60.iloc[-1] > 0 else 0
        }
    }


def detect_choppy_bear_vectorized(
    df: pd.DataFrame,
    cum_ret_th: float = -0.05,
    volatility_th: float = 0.18,
    ma60_slope_th: float = 0.00025,
    score_threshold: int = 3,
) -> pd.Series:
    """震荡下行检测向量化版本（O(n)）"""
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    log_ret = np.log(close / close.shift(1))

    cum_ret_60d = close / close.shift(60) - 1
    vol_60d = log_ret.rolling(60).std() * np.sqrt(252)
    # MA60 20 日斜率：(今日 - 20 日前) / 20 日前
    ma60_slope = (ma60 - ma60.shift(20)) / (ma60.shift(20) + 1e-9)

    cond_1 = cum_ret_60d < cum_ret_th
    cond_2 = vol_60d < volatility_th
    cond_3 = ma60_slope.abs() < ma60_slope_th
    cond_4 = ma20 < ma60

    score = (
        cond_1.fillna(False).astype(int) +
        cond_2.fillna(False).astype(int) +
        cond_3.fillna(False).astype(int) +
        cond_4.fillna(False).astype(int)
    )

    return (score >= score_threshold).fillna(False).astype(bool)
