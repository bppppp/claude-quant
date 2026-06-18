"""因子合成"""
import numpy as np
import pandas as pd


def synthesize_equal_weight(factor_dict: dict) -> pd.Series:
    """等权合成"""
    return sum(factor_dict.values()) / len(factor_dict)


def synthesize_ic_weight(factor_dict: dict,
                          ic_series_dict: dict,
                          lookback: int = 120) -> pd.Series:
    """IC 加权合成（按 |IC| 平均）"""
    weights = {}
    for name, ic_series in ic_series_dict.items():
        recent_ic = ic_series.iloc[-lookback:].abs().mean()
        weights[name] = recent_ic

    total = sum(weights.values())
    if total == 0:
        return synthesize_equal_weight(factor_dict)

    weights = {k: v / total for k, v in weights.items()}

    composite = None
    for name, factor in factor_dict.items():
        if name in weights:
            weighted = factor * weights[name]
            composite = weighted if composite is None else composite + weighted

    return composite
