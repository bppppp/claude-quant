"""动态因子权重（按市场状态 + spec §7.3 状态偏向）

spec §7.3：动态调整
- 牛市中动量因子权重×1.5
- 震荡市中量价反转因子权重×1.5
- 熊市中低波/质量因子权重×1.5

实现方式：基础权重 → 按状态×1.5 强调对应类 → 归一化
"""
from enum import Enum
from typing import Dict


class MarketState(str, Enum):
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"
    CRASH = "CRASH"
    CHOPPY_BEAR = "CHOPPY_BEAR"


# spec §7.3 因子分类
MOMENTUM_FACTORS = {"ret_20d", "ret_60d", "sharpe_60d"}
MEAN_REVERSION_FACTORS = {"vol_ratio_5_20", "turnover_stability", "corr_ret_vol", "rsi_14_centered", "near_high_60"}
LOW_VOL_QUALITY_FACTORS = {"sharpe_60d", "turnover_stability", "rsi_14_centered", "bb_width"}

EMPHASIS_MULT = 1.5  # spec §7.3 强调倍数


def _validate_weights(weights: dict, tolerance: float = 0.01) -> bool:
    """校验权重总和 ≈ 1.0"""
    total = sum(weights.values())
    return abs(total - 1.0) < tolerance


def _normalize(weights: dict) -> dict:
    """归一化使总和 = 1.0"""
    total = sum(abs(v) for v in weights.values())
    if total <= 0:
        return weights
    return {k: v / total for k, v in weights.items()}


# 基础权重（按状态分组）
_BASE_WEIGHTS: Dict[MarketState, dict] = {
    MarketState.BULL: {
        "trend_ma60": 0.10,
        "ma_slope_60": 0.08,
        "adx_14": 0.05,
        "price_above_ma120": 0.04,
        "ret_20d": 0.15,
        "ret_60d": 0.12,
        "sharpe_60d": 0.06,
        "vol_ratio_5_20": 0.10,
        "turnover_stability": 0.05,
        "corr_ret_vol": 0.05,
        "rsi_14_centered": 0.10,
        "near_high_60": 0.05,
        "bb_width": 0.05,
    },
    MarketState.SIDEWAYS: {
        "trend_ma60": 0.06,
        "ma_slope_60": 0.05,
        "adx_14": 0.03,
        "price_above_ma120": 0.04,
        "ret_20d": 0.08,
        "ret_60d": 0.05,
        "sharpe_60d": 0.10,
        "vol_ratio_5_20": 0.12,
        "turnover_stability": 0.10,
        "corr_ret_vol": 0.10,
        "rsi_14_centered": 0.15,
        "near_high_60": 0.07,
        "bb_width": 0.05,
    },
    MarketState.BEAR: {
        "trend_ma60": 0.08,
        "ma_slope_60": 0.05,
        "adx_14": 0.03,
        "price_above_ma120": 0.08,
        "ret_20d": 0.06,
        "ret_60d": 0.05,
        "sharpe_60d": 0.12,
        "vol_ratio_5_20": 0.06,
        "turnover_stability": 0.15,
        "corr_ret_vol": 0.06,
        "rsi_14_centered": 0.15,
        "near_high_60": 0.05,
        "bb_width": 0.06,
    },
    MarketState.CRASH: {
        "sharpe_60d": 0.40,
        "turnover_stability": 0.30,
        "rsi_14_centered": 0.30,
    },
    MarketState.CHOPPY_BEAR: {
        "trend_ma60": 0.05,
        "ma_slope_60": 0.03,
        "adx_14": 0.02,
        "price_above_ma120": 0.10,
        "ret_20d": 0.05,
        "ret_60d": 0.05,
        "sharpe_60d": 0.15,
        "vol_ratio_5_20": 0.08,
        "turnover_stability": 0.15,
        "corr_ret_vol": 0.10,
        "rsi_14_centered": 0.10,
        "near_high_60": 0.07,
        "bb_width": 0.05,
    },
}


def _apply_emphasis(weights: dict, emphasize_set: set, mult: float = EMPHASIS_MULT) -> dict:
    """对指定因子集合应用 ×1.5 强调，再归一化"""
    boosted = {k: (v * mult if k in emphasize_set else v) for k, v in weights.items()}
    return _normalize(boosted)


def get_factor_weights(state: str) -> dict:
    """根据市场状态获取因子权重（spec §7.3 状态偏向已应用）"""
    try:
        ms = MarketState(state)
    except (ValueError, KeyError):
        ms = MarketState.SIDEWAYS

    base = _BASE_WEIGHTS[ms]

    # spec §7.3 状态偏向
    if ms == MarketState.BULL:
        return _apply_emphasis(base, MOMENTUM_FACTORS)
    elif ms == MarketState.SIDEWAYS:
        return _apply_emphasis(base, MEAN_REVERSION_FACTORS)
    elif ms == MarketState.BEAR:
        return _apply_emphasis(base, LOW_VOL_QUALITY_FACTORS)
    elif ms == MarketState.CHOPPY_BEAR:
        return _apply_emphasis(base, MEAN_REVERSION_FACTORS)
    else:  # CRASH
        return _normalize(base)


# 向后兼容：FACTOR_WEIGHTS 字典（对外接口不变）
FACTOR_WEIGHTS: Dict[MarketState, dict] = {
    ms: get_factor_weights(ms.value) for ms in MarketState
}
