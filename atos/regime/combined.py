"""综合状态层（市场状态 + 震荡下行叠加）"""
import numpy as np
import pandas as pd


def compute_combined_regime(
    regime_state: pd.Series,
    choppy_bear: pd.Series,
    choppy_bear_grace_days: int = 3,
) -> pd.DataFrame:
    """综合状态（市场状态 + 震荡下行叠加）

    Returns:
        DataFrame with columns: [state, choppy_bear, effective_state, target_position, mode_pnl, transition_position]
    """
    df = pd.DataFrame({
        "state": regime_state,
        "choppy_bear": choppy_bear.astype(bool),
    })

    # 计算 choppy_bear 生效期
    choppy_bear_active = df["choppy_bear"].copy()

    for i in range(1, len(df)):
        if (df["choppy_bear"].iloc[i] == False
                and df["choppy_bear"].iloc[i-1] == True):
            current_state = df["state"].iloc[i]
            if current_state == "CRASH":
                choppy_bear_active.iloc[i] = False
            elif current_state == "BULL":
                end_idx = min(i + choppy_bear_grace_days, len(df))
                choppy_bear_active.iloc[i:end_idx] = True
            # BEAR/SIDEWAYS：保持 False

    df["choppy_bear_active"] = choppy_bear_active
    df["effective_state"] = np.where(
        df["choppy_bear_active"],
        "CHOPPY_BEAR",
        df["state"]
    )

    base_position = {
        "BULL": 0.85,
        "SIDEWAYS": 0.55,
        "BEAR": 0.15,
        "CRASH": 0.05,
        "CHOPPY_BEAR": 0.15,
    }
    df["base_target_position"] = df["effective_state"].map(base_position)

    # 延后撤销期间仓位线性插值
    df["transition_position"] = df["base_target_position"]
    for i in range(1, len(df)):
        if (df["choppy_bear"].iloc[i] == False
                and df["choppy_bear"].iloc[i-1] == True
                and df["state"].iloc[i] == "BULL"):
            for day_offset in range(choppy_bear_grace_days):
                idx = min(i + day_offset, len(df) - 1)
                if df["choppy_bear_active"].iloc[idx]:
                    ratio = (day_offset + 1) / (choppy_bear_grace_days + 1)
                    df.iloc[idx, df.columns.get_loc("transition_position")] = (
                        0.15 + (0.85 - 0.15) * ratio
                    )

    df["target_position"] = df["transition_position"]
    df["mode_pnl"] = 0.0

    return df


def detect_full_regime(df: pd.DataFrame, config=None) -> pd.DataFrame:
    """完整的 4 状态 + 震荡下行检测流程

    Args:
        df: 含 open/high/low/close/volume + MA20/MA60/MA120 + 指标的 DataFrame
        config: StrategyConfig

    Returns:
        完整的每日状态信息
    """
    from .market_regime import detect_market_regime
    from .hysteresis import apply_hysteresis_with_crash_override
    from .choppy_bear import detect_choppy_bear_vectorized

    # 1. 原始 4 状态（ATOS2 v2: 加 ADX/RSI 前瞻）
    cfg_crash_5d = getattr(config, "crash_5d_drawdown", -0.08)
    cfg_crash_20d = getattr(config, "crash_20d_drawdown", -0.15)
    cfg_crash_vol = getattr(config, "crash_volatility_th", 0.35)
    cfg_adx_bull = getattr(config, "adx_bull_threshold", 0.0) if config else 0.0
    cfg_rsi_bear = getattr(config, "rsi_bear_threshold", 100.0) if config else 100.0
    regime_raw = detect_market_regime(
        df,
        crash_5d_drawdown=cfg_crash_5d,
        crash_20d_drawdown=cfg_crash_20d,
        crash_volatility_th=cfg_crash_vol,
        adx_bull_th=cfg_adx_bull,
        rsi_bear_th=cfg_rsi_bear,
    )

    # 2. 状态迟滞
    min_dur = getattr(config, "min_duration", 3)
    cooldown = getattr(config, "cooldown_days", 5)
    state_confirmed = apply_hysteresis_with_crash_override(
        regime_raw["state"], min_duration=min_dur, cooldown=cooldown
    )

    # 3. 震荡下行检测（向量化）
    choppy_bear = detect_choppy_bear_vectorized(df)

    # 4. 综合状态
    grace_days = getattr(config, "choppy_bear_grace_days", 3) if config else 3
    combined = compute_combined_regime(
        state_confirmed, choppy_bear, choppy_bear_grace_days=grace_days
    )

    return combined
