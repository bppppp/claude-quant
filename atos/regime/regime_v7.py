"""ATOS7 v1: 5 状态识别（Weinstein Stage Analysis 启发）

5 状态:
- STAGE_1_BASING (筑底)
- STAGE_2_ADVANCING (上升)
- STAGE_3_TOPPING (顶部)
- STAGE_4_DECLINING (下降)
- CRASH (暴跌)
"""
import numpy as np
import pandas as pd


def detect_regime_v7(df: pd.DataFrame,
                     crash_5d_drawdown: float = -0.04,
                     crash_20d_drawdown: float = -0.10,
                     crash_volume_spike: float = 2.0,
                     stage2_ma200_slope_th: float = 0.02,
                     stage4_drawdown_th: float = -0.25) -> pd.DataFrame:
    """ATOS7 v1: 5 状态识别

    Returns:
        DataFrame with columns: [stage, realized_vol_20d, ...]
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # 关键均线
    ma50 = df["MA60"]  # 用 MA60 代替
    ma150 = df["MA150"] if "MA150" in df.columns else df["MA120"]
    ma200 = df["MA200"] if "MA200" in df.columns else df["MA120"]

    # 52 周高低
    high_52w = close.rolling(252, min_periods=60).max()
    low_52w = close.rolling(252, min_periods=60).min()

    # MA200 1 月斜率
    ma200_slope = (ma200 / ma200.shift(20) - 1).fillna(0)

    # CRASH 判定（保留 v6 逻辑）
    drawdown_5d = close / close.shift(5) - 1
    drawdown_20d = close / close.shift(20) - 1
    log_ret = np.log(close / close.shift(1))
    realized_vol_20d = log_ret.rolling(20).std() * np.sqrt(252)

    crash_basic = (drawdown_5d <= crash_5d_drawdown) | (drawdown_20d <= crash_20d_drawdown)
    if "amount" in df.columns:
        amt_ratio = df["amount"] / df["amount"].rolling(20).mean()
        crash_volume = (amt_ratio > crash_volume_spike) & (drawdown_5d < -0.03)
    else:
        crash_volume = pd.Series(False, index=df.index)
    is_crash = (crash_basic | crash_volume).fillna(False)

    # STAGE_2_ADVANCING: 5 条件全满足
    is_stage2 = (
        (close > ma150) &
        (ma150 > ma200) &
        (ma200_slope > stage2_ma200_slope_th) &
        (close > low_52w * 1.30) &
        (close > high_52w * 0.75)  # 在 52 周高点 25% 内
    ).fillna(False)

    # STAGE_4_DECLINING: 3 条件全满足
    is_stage4 = (
        (close < ma150) &
        (ma150 < ma200) &
        (close < high_52w * (1 + stage4_drawdown_th))  # 距高点 > 25%
    ).fillna(False)

    # STAGE_1_BASING: MA200 走平 + 价格回 MA200 + 不在 S2/S4
    ma200_flat = ma200_slope.abs() < 0.0001
    near_ma200 = (close / ma200 - 1).abs() < 0.05
    is_stage1 = (ma200_flat & near_ma200 & ~is_stage2 & ~is_stage4 & ~is_crash).fillna(False)

    # STAGE_3_TOPPING: 1 月前是 S2，现在不是 S2 也不是 S4
    # 简化：MA50 < MA150（即将死叉）+ 价格 > MA200
    is_stage3 = (
        (close > ma200) &  # 仍在 MA200 上方
        (ma50 < ma150) &  # 短期均线死叉中
        ~is_stage2 &
        ~is_stage4 &
        ~is_crash
    ).fillna(False)

    # 优先级：CRASH > S2 > S4 > S3 > S1 > SIDEWAYS
    stage = pd.Series("SIDEWAYS", index=df.index, dtype=object)
    stage[is_crash] = "CRASH"
    stage[is_stage2 & ~is_crash] = "STAGE_2"
    stage[is_stage4 & ~is_crash & ~is_stage2] = "STAGE_4"
    stage[is_stage3 & ~is_crash & ~is_stage2 & ~is_stage4] = "STAGE_3"
    stage[is_stage1 & ~is_crash & ~is_stage2 & ~is_stage4 & ~is_stage3] = "STAGE_1"

    return pd.DataFrame({
        "stage": stage,
        "is_stage1": is_stage1,
        "is_stage2": is_stage2,
        "is_stage3": is_stage3,
        "is_stage4": is_stage4,
        "is_crash": is_crash,
        "ma200_slope": ma200_slope,
        "realized_vol_20d": realized_vol_20d,
        "drawdown_5d": drawdown_5d,
        "drawdown_20d": drawdown_20d,
    })
