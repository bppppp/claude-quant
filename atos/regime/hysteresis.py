"""状态迟滞机制 - 用交易日计算冷却期"""
import numpy as np
import pandas as pd


def apply_hysteresis(
    state: pd.Series,
    min_duration: int = 3,
    cooldown: int = 5,
) -> pd.Series:
    """状态迟滞机制（用交易日而非索引差）

    Args:
        state: 原始状态序列
        min_duration: 连续 N 日满足才切换
        cooldown: 切换后冷却期（交易日）

    Returns:
        确认后的状态 Series
    """
    if len(state) == 0:
        return state.copy()

    result = [state.iloc[0]]
    candidate = state.iloc[0]
    candidate_count = 0
    last_switch_date = None

    for i in range(1, len(state)):
        proposed = state.iloc[i]
        current_date = state.index[i]

        # 冷却期内保持现状
        if last_switch_date is not None:
            trading_days_since_switch = np.busday_count(
                last_switch_date.date(),
                current_date.date()
            )
            if trading_days_since_switch < cooldown:
                if proposed == "CRASH":
                    result.append("CRASH")
                    last_switch_date = current_date
                    continue
                result.append(result[-1])
                continue

        if proposed == result[-1]:
            result.append(proposed)
            candidate = proposed
            candidate_count = 0
        else:
            if proposed == candidate:
                candidate_count += 1
            else:
                candidate = proposed
                candidate_count = 1

            if candidate_count >= min_duration:
                result.append(proposed)
                last_switch_date = current_date
                candidate = proposed
                candidate_count = 0
            else:
                result.append(result[-1])

    return pd.Series(result, index=state.index, name="regime_confirmed")


def apply_hysteresis_with_crash_override(
    state: pd.Series,
    min_duration: int = 3,
    cooldown: int = 5,
) -> pd.Series:
    """带 CRASH 例外的状态迟滞

    CRASH 立即切换（无视冷却期）
    """
    if len(state) == 0:
        return state.copy()

    result = [state.iloc[0]]
    candidate = state.iloc[0]
    candidate_count = 0
    last_switch_date = None

    for i in range(1, len(state)):
        proposed = state.iloc[i]
        current_date = state.index[i]

        if proposed == "CRASH":
            result.append("CRASH")
            last_switch_date = current_date
            candidate = "CRASH"
            candidate_count = 0
            continue

        if last_switch_date is not None:
            trading_days_since_switch = np.busday_count(
                last_switch_date.date(),
                current_date.date()
            )
            if trading_days_since_switch < cooldown:
                result.append(result[-1])
                continue

        if proposed == result[-1]:
            result.append(proposed)
            candidate = proposed
            candidate_count = 0
        else:
            if proposed == candidate:
                candidate_count += 1
            else:
                candidate = proposed
                candidate_count = 1

            if candidate_count >= min_duration:
                result.append(proposed)
                last_switch_date = current_date
                candidate = proposed
                candidate_count = 0
            else:
                result.append(result[-1])

    return pd.Series(result, index=state.index, name="regime_confirmed")
