"""ATOS9 v1: 纯均值回归入场信号
- 入场: RSI(6) < 30 OR BB下轨 OR 20日新低+阳线 OR 连跌 OR 量缩
- 出场: RSI(6) > 50 OR +5% OR -3% OR 5天
"""
import pandas as pd
import numpy as np


def _get_series(df, col):
    """从 df 拿列（处理重复列 DataFrame）"""
    val = df[col]
    if isinstance(val, pd.DataFrame):
        # 重复列 - 取第一个
        return val.iloc[:, 0]
    return val


def signal_mean_reversion_entry(df: pd.DataFrame, top_n: int = 5,
                                  rsi_th: float = 35.0,
                                  drop_th: float = -0.08) -> pd.Series:
    """ATOS9 v1+: 均值回归入场信号

    Args:
        rsi_th: RSI 阈值（v2: 30→25 更严）
        drop_th: 5日跌幅阈值（v2: -0.10→-0.08 更宽）
    """
    rsi6 = _get_series(df, "RSI6") if "RSI6" in df.columns else pd.Series(50, index=df.index)
    close = _get_series(df, "close")
    low = _get_series(df, "low")
    vol = _get_series(df, "volume")

    # 5 个 OR 条件（v2: 更严的入场）
    cond1 = (rsi6 < rsi_th).fillna(False)
    if "BOLL_DOWN" in df.columns:
        boll_down = _get_series(df, "BOLL_DOWN")
        cond2 = (boll_down > close).fillna(False)
    else:
        cond2 = pd.Series(False, index=df.index)
    cond3 = (close <= low.rolling(20).min() * 1.01).fillna(False)
    cond4 = (close / close.shift(5) - 1 < drop_th).fillna(False)
    cond5 = (vol < vol.rolling(20).mean() * 0.5).fillna(False)

    is_entry = (cond1 | cond2 | cond3 | cond4 | cond5).fillna(False).astype(int)
    return is_entry


def signal_mean_reversion_exit(df: pd.DataFrame, entry_price: float,
                                entry_date: pd.Timestamp,
                                current_date: pd.Timestamp) -> tuple:
    """ATOS9 v1: 均值回归出场信号

    Returns: (should_exit, reason)
    """
    if entry_date == current_date:
        return False, ""

    rsi6 = df.loc[current_date, "RSI6"] if "RSI6" in df.columns else 50
    current_price = df.loc[current_date, "close"]
    ret = (current_price / entry_price - 1) if entry_price > 0 else 0
    days_held = (current_date - entry_date).days

    if rsi6 > 50:
        return True, "RSI恢复"
    if ret >= 0.05:
        return True, "止盈+5%"
    if ret <= -0.03:
        return True, "止损-3%"
    if days_held >= 5:
        return True, "时间止损5天"

    return False, ""
