"""趋势类指标：MA、MACD、DMI/ADX、均线粘合度、均线排列"""
import numpy as np
import pandas as pd

from .base import wilder_smooth


def calc_ma(close: pd.Series,
            periods=(5, 10, 20, 60, 120, 250)) -> pd.DataFrame:
    """简单移动平均线"""
    return pd.DataFrame({
        f"MA{p}": close.rolling(window=p, min_periods=1).mean()
        for p in periods
    })


def calc_ema(close: pd.Series,
             periods=(5, 10, 20, 60)) -> pd.DataFrame:
    """指数移动平均线"""
    return pd.DataFrame({
        f"EMA{p}": close.ewm(span=p, adjust=False).mean()
        for p in periods
    })


def calc_ma_alignment(close: pd.Series,
                      fast: int = 5,
                      mid: int = 10,
                      slow: int = 20,
                      very_slow: int = 60) -> pd.Series:
    """均线排列强度 [0, 1]：多头=1，空头=0"""
    ma_f = close.rolling(fast, min_periods=1).mean()
    ma_m = close.rolling(mid, min_periods=1).mean()
    ma_s = close.rolling(slow, min_periods=1).mean()
    ma_vs = close.rolling(very_slow, min_periods=1).mean()

    score = pd.Series(0.0, index=close.index)
    score += (ma_f > ma_m).astype(float) * 0.25
    score += (ma_m > ma_s).astype(float) * 0.25
    score += (ma_s > ma_vs).astype(float) * 0.25
    score += (ma_f > ma_s).astype(float) * 0.25
    return score


def calc_ma_convergence(close: pd.Series,
                         fast: int = 5,
                         mid: int = 10,
                         slow: int = 20) -> pd.Series:
    """均线粘合度：(max-min)/close，越小越粘合"""
    ma_f = close.rolling(fast, min_periods=1).mean()
    ma_m = close.rolling(mid, min_periods=1).mean()
    ma_s = close.rolling(slow, min_periods=1).mean()
    max_ma = pd.concat([ma_f, ma_m, ma_s], axis=1).max(axis=1)
    min_ma = pd.concat([ma_f, ma_m, ma_s], axis=1).min(axis=1)
    return (max_ma - min_ma) / (close + 1e-9)


def calc_macd(close: pd.Series,
              fast: int = 12,
              slow: int = 26,
              signal: int = 9) -> pd.DataFrame:
    """MACD 指标：DIF, DEA, MACD"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_bar = (dif - dea) * 2
    return pd.DataFrame({"DIF": dif, "DEA": dea, "MACD": macd_bar})


def macd_golden_cross(macd_df: pd.DataFrame) -> pd.Series:
    dif = macd_df["DIF"]
    dea = macd_df["DEA"]
    return ((dif > dea) & (dif.shift(1) <= dea.shift(1))).astype(int)


def macd_death_cross(macd_df: pd.DataFrame) -> pd.Series:
    dif = macd_df["DIF"]
    dea = macd_df["DEA"]
    return ((dif < dea) & (dif.shift(1) >= dea.shift(1))).astype(int)


def calc_dmi_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                 period: int = 14) -> pd.DataFrame:
    """DMI/ADX 指标"""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=close.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=close.index
    )

    atr = wilder_smooth(tr, period)
    pdi = 100 * wilder_smooth(plus_dm, period) / atr.replace(0, np.nan)
    ndi = 100 * wilder_smooth(minus_dm, period) / atr.replace(0, np.nan)
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    adx = wilder_smooth(dx.fillna(0), period)

    return pd.DataFrame({
        "PDI": pdi.fillna(0),
        "NDI": ndi.fillna(0),
        "DX": dx.fillna(0),
        "ADX": adx.fillna(0),
    })
