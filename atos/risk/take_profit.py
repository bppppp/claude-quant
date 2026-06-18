"""移动止盈 + 分批止盈计算"""
import numpy as np


def compute_trailing_stop(highest_price: float, current_atr: float, k: float = 2.0) -> float:
    return highest_price - k * current_atr


def update_trailing_stop(current_trailing_stop: float, new_highest: float,
                          new_atr: float, k: float = 2.0) -> float:
    new_stop = compute_trailing_stop(new_highest, new_atr, k)
    return max(current_trailing_stop, new_stop)
