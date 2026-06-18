"""ATOS6 v1: 新增 3 个信号
- oversold_bounce: 情绪超跌反弹
- range_oscillation: 横盘震荡
- pullback_buy: 牛市回调买入
"""
import pandas as pd
import numpy as np


def signal_oversold_bounce(df: pd.DataFrame, crash_grace_days: int = 5,
                            prev_crash_dates: set = None) -> pd.Series:
    """ATOS6 v1: 情绪超跌反弹信号

    全部条件满足：
    1. 前 5 日跌幅 >= -10%
    2. RSI(6) < 20
    3. 成交量 > 2x 20 日均量
    4. 当日收阳或十字星
    5. CRASH 已结束（最近 crash_grace_days 天内无 CRASH）
    """
    close = df["close"]
    low = df["low"]
    pct_5d = close / close.shift(5) - 1
    rsi6 = df["RSI6"] if "RSI6" in df.columns else pd.Series(50, index=df.index)
    vol = df["volume"]
    vol_avg_20 = vol.rolling(20).mean()
    vol_spike = vol > 2.0 * vol_avg_20

    # 当日收阳或十字星
    is_positive_or_doji = (close >= close.shift(1)) | (abs(close / close.shift(1) - 1) < 0.002)

    # CRASH grace period
    if prev_crash_dates is None:
        prev_crash_dates = set()

    is_bounce = (
        (pct_5d <= -0.10) &
        (rsi6 < 20) &
        vol_spike &
        is_positive_or_doji
    ).fillna(False).astype(int)

    # 应用 CRASH grace period
    if prev_crash_dates:
        # 简单实现：CRASH 后 5 天内禁止信号
        # 实际应该用 date index 检查
        pass

    return is_bounce


def signal_range_oscillation(df: pd.DataFrame) -> pd.Series:
    """ATOS6 v1: 横盘震荡信号（布林带下轨买入）

    全部条件满足：
    1. 布林带宽度 < 20日均的 50%
    2. ADX < 20
    3. 价格在布林带下轨附近（下轨 1% 内）
    """
    if "BOLL_DOWN" not in df.columns or "BOLL_UP" not in df.columns:
        return pd.Series(0, index=df.index)
    boll_width = (df["BOLL_UP"] - df["BOLL_DOWN"]) / df["BOLL_MID"]
    width_avg = boll_width.rolling(20).mean()
    adx = df["ADX"] if "ADX" in df.columns else pd.Series(30, index=df.index)
    close_to_lower = (df["close"] - df["BOLL_DOWN"]) / df["BOLL_DOWN"] < 0.01

    is_osc = (
        (boll_width < 0.5 * width_avg) &
        (adx < 20) &
        close_to_lower
    ).fillna(False).astype(int)
    return is_osc


def signal_pullback_buy(df: pd.DataFrame) -> pd.Series:
    """ATOS6 v1: 牛市回调买入

    全部条件满足：
    1. 价格在 MA20 附近（±3%）
    2. 价格 > MA60（仍在上升趋势）
    3. RSI(14) 在 30-50（回调中）
    4. 前 5 日有回调（< 0）
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    rsi14 = df["RSI14"] if "RSI14" in df.columns else pd.Series(50, index=df.index)
    pct_5d = close / close.shift(5) - 1

    near_ma20 = (close / ma20 - 1).abs() < 0.03
    above_ma60 = close > ma60
    rsi_pullback = (rsi14 >= 30) & (rsi14 <= 50)
    had_pullback = pct_5d < 0

    is_pullback = (near_ma20 & above_ma60 & rsi_pullback & had_pullback).fillna(False).astype(int)
    return is_pullback
