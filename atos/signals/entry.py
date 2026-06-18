"""6 类买点"""
import numpy as np
import pandas as pd


def signal_ma_macd(df: pd.DataFrame) -> pd.Series:
    """买点 1：MA5 上穿 MA10 金叉"""
    ma5 = df["MA5"]
    ma10 = df["MA10"]
    golden_cross = (ma5 > ma10) & (ma5.shift(1) <= ma10.shift(1))
    return golden_cross.fillna(False).astype(int)


def signal_kdj_rsi(df: pd.DataFrame) -> pd.Series:
    """买点 2：KDJ 金叉 + K/D 阈值 + RSI 确认"""
    k = df["K"]
    d = df["D"]
    rsi6 = df["RSI6"]
    rsi12 = df["RSI12"]
    cond1 = (k > d) & (k.shift(1) <= d.shift(1))
    cond2 = (k < 80) & (d < 70)
    cond3 = (rsi6 > 20) & (rsi12 > 30)
    return (cond1 & cond2 & cond3).fillna(False).astype(int)


def signal_boll_volume(df: pd.DataFrame) -> pd.Series:
    """买点 3：布林下轨 + 量能 + RSI 超卖

    修复 A11：昨日 <= 下轨 AND 今日 > 下轨（真正反弹）
    """
    close = df["close"]
    close_prev = close.shift(1)
    boll_low = df["BOLL_DOWN"]
    boll_mid = df["BOLL_MID"]
    vol = df["volume"]
    rsi6 = df["RSI6"]
    vol_ma5 = vol.rolling(5, min_periods=1).mean()

    cond1 = (close_prev <= boll_low * 1.001)
    cond2 = close > boll_low
    cond3 = close > close_prev
    cond4 = vol > vol_ma5 * 1.2
    cond5 = rsi6 < 35
    cond6 = close > boll_mid * 0.90
    return (cond1 & cond2 & cond3 & cond4 & cond5 & cond6).fillna(False).astype(int)


def signal_donchian_breakout(df: pd.DataFrame) -> pd.Series:
    """买点 4：Donchian 突破 + 放量 + ADX > 20"""
    close = df["close"]
    dc_up_prev = df["DC_UP"].shift(1)
    vol = df["volume"]
    vol_ma20 = vol.rolling(20, min_periods=1).mean()
    adx = df["ADX"]
    return ((close > dc_up_prev) & (vol > vol_ma20 * 1.5) & (adx > 20)).fillna(False).astype(int)


def signal_macd_bottom_divergence(df: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """买点 5：MACD 底背离（向量化）"""
    close = df["close"]
    macd = df["MACD"]
    # 价新低，MACD 不新低
    rolling_min_close = close.rolling(lookback, min_periods=lookback).min()
    rolling_min_macd = macd.rolling(lookback, min_periods=lookback).min()
    price_new_low = close <= rolling_min_close
    macd_not_new_low = macd >= rolling_min_macd
    return (price_new_low & macd_not_new_low).fillna(False).astype(int)


def signal_ma_converge_break(df: pd.DataFrame) -> pd.Series:
    """买点 6：均线粘合后突破"""
    ma5 = df["MA5"]
    ma10 = df["MA10"]
    ma20 = df["MA20"]
    close = df["close"]
    vol = df["volume"]
    vol_ma20 = vol.rolling(20, min_periods=1).mean()

    converge = (
        ((ma5 / ma20 - 1).abs() < 0.02) &
        ((ma5 / ma10 - 1).abs() < 0.02) &
        ((ma10 / ma20 - 1).abs() < 0.02)
    )
    breakout = close > ma20
    recent = breakout & (~breakout.shift(1).fillna(False))
    return (converge.shift(1).fillna(False) & recent & (vol > vol_ma20 * 1.2)).fillna(False).astype(int)


def generate_buy_signals(df: pd.DataFrame, regime: str, config=None,
                          adaptive_open_threshold: float = None) -> pd.DataFrame:
    """生成买点信号（按市场状态分级）

    Args:
        adaptive_open_threshold: spec §6.1 自适应开仓阈值（None 时用 config 默认）

    Returns:
        DataFrame: 各买点信号 + weighted_score + final
    """
    signals = pd.DataFrame({
        "sig_ma_macd": signal_ma_macd(df),
        "sig_kdj_rsi": signal_kdj_rsi(df),
        "sig_boll_vol": signal_boll_volume(df),
        "sig_dc_break": signal_donchian_breakout(df),
        "sig_macd_div": signal_macd_bottom_divergence(df),
        "sig_ma_conv": signal_ma_converge_break(df)
    }, index=df.index)

    # ATOS6 v1: 集成 3 个新信号
    try:
        from .v6_signals import signal_oversold_bounce, signal_range_oscillation, signal_pullback_buy
        signals["sig_oversold_bounce"] = signal_oversold_bounce(df)
        signals["sig_range_osc"] = signal_range_oscillation(df)
        signals["sig_pullback_buy"] = signal_pullback_buy(df)
    except Exception:
        pass

    # ATOS9 v1: 集成均值回归入场信号
    try:
        from .mean_reversion import signal_mean_reversion_entry
        signals["sig_mean_reversion"] = signal_mean_reversion_entry(df)
    except Exception:
        pass

    PRIMARY_SIGNALS = {
        "BULL": ["sig_ma_macd", "sig_dc_break", "sig_pullback_buy"],
        "SIDEWAYS": ["sig_mean_reversion", "sig_kdj_rsi", "sig_range_osc"],  # ATOS9 v1: 主信号=均值回归
        "BEAR": ["sig_mean_reversion", "sig_macd_div", "sig_oversold_bounce"],  # ATOS9 v1: 主信号=均值回归
        "CHOPPY_BEAR": ["sig_mean_reversion", "sig_macd_div", "sig_oversold_bounce"],
    }
    SECONDARY_SIGNALS = {
        "BULL": ["sig_ma_conv"],
        "SIDEWAYS": ["sig_boll_vol", "sig_oversold_bounce"],
        "BEAR": ["sig_boll_vol", "sig_range_osc"],
        "CHOPPY_BEAR": [],
    }

    if regime == "CRASH":
        signals["weighted_score"] = 0
        signals["final"] = 0
        return signals

    primary = PRIMARY_SIGNALS.get(regime, [])
    secondary = SECONDARY_SIGNALS.get(regime, [])

    primary_score = sum(signals[s] for s in primary if s in signals.columns) * 2
    secondary_score = sum(signals[s] for s in secondary if s in signals.columns)
    max_score = (len(primary) * 2 + len(secondary)) if (primary or secondary) else 1
    signals["weighted_score"] = (primary_score + secondary_score) / max_score

    if config is not None and hasattr(config, "open_threshold_by_regime"):
        thresholds = config.open_threshold_by_regime
    else:
        thresholds = {
            "BULL": 0.70, "SIDEWAYS": 0.60, "BEAR": 0.75, "CHOPPY_BEAR": 0.75,
        }
    # spec §6.1 自适应开仓阈值
    if adaptive_open_threshold is not None:
        threshold = adaptive_open_threshold
    else:
        threshold = thresholds.get(regime, 0.70)
    signals["final"] = (signals["weighted_score"] >= threshold).astype(int)

    # 辅信号阈值：≥2 个辅信号同时触发
    if secondary:
        sec_count = sum(signals[s] for s in secondary if s in signals.columns)
        sec_only = (signals["weighted_score"] == 0) & (sec_count >= 2)
        signals.loc[sec_only, "final"] = 1

    return signals
