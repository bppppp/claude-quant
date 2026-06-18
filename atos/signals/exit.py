"""4 类卖点"""
import numpy as np
import pandas as pd


def signal_ma_macd_death(df: pd.DataFrame) -> pd.Series:
    """卖点 1：MA5 下穿 MA10 死叉"""
    ma5 = df["MA5"]
    ma10 = df["MA10"]
    death_cross = (ma5 < ma10) & (ma5.shift(1) >= ma10.shift(1))
    return death_cross.fillna(False).astype(int)


def signal_kdj_overbought_death(df: pd.DataFrame) -> pd.Series:
    """卖点 2：KDJ 超买死叉（K > 80, D > 70 后 K 下穿 D）"""
    k = df["K"]
    d = df["D"]
    cond1 = (k < d) & (k.shift(1) >= d.shift(1))
    cond2 = (k.shift(1) > 80) & (d.shift(1) > 70)
    return (cond1 & cond2).fillna(False).astype(int)


def signal_boll_mid_break(df: pd.DataFrame) -> pd.Series:
    """卖点 3：跌破布林中轨"""
    close = df["close"]
    boll_mid = df["BOLL_MID"]
    return ((close < boll_mid) & (close.shift(1) >= boll_mid.shift(1))).fillna(False).astype(int)


def signal_macd_top_divergence(df: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """卖点 4：MACD 顶背离（向量化）"""
    close = df["close"]
    macd = df["MACD"]
    rolling_max_close = close.rolling(lookback, min_periods=lookback).max()
    rolling_max_macd = macd.rolling(lookback, min_periods=lookback).max()
    price_new_high = close >= rolling_max_close
    macd_not_new_high = macd <= rolling_max_macd
    return (price_new_high & macd_not_new_high).fillna(False).astype(int)


def generate_sell_signals(df: pd.DataFrame) -> pd.DataFrame:
    """生成所有卖点信号"""
    signals = pd.DataFrame({
        "sig_ma_macd_death": signal_ma_macd_death(df),
        "sig_kdj_over_death": signal_kdj_overbought_death(df),
        "sig_boll_mid": signal_boll_mid_break(df),
        "sig_macd_top_div": signal_macd_top_divergence(df)
    }, index=df.index)

    signals["any_sell"] = signals.any(axis=1).astype(int)
    return signals
