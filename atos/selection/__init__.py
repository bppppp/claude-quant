"""selection 模块"""
from .factors import calc_all_factors
from .preprocessing import (
    winsorize_mad, winsorize_3sigma,
    standardize_zscore, standardize_rank,
    neutralize, preprocess_factor,
)
from .synthesis import synthesize_equal_weight, synthesize_ic_weight
from .weight_schedule import get_factor_weights, FACTOR_WEIGHTS, MarketState
from .selector import StockSelector


__all__ = [
    "calc_all_factors",
    "winsorize_mad", "winsorize_3sigma",
    "standardize_zscore", "standardize_rank",
    "neutralize", "preprocess_factor",
    "synthesize_equal_weight", "synthesize_ic_weight",
    "get_factor_weights", "FACTOR_WEIGHTS", "MarketState",
    "StockSelector",
]
