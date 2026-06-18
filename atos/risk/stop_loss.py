"""5 层止损检查"""
import numpy as np
import pandas as pd

from .position import Position


def check_exit(position: Position,
                current_price: float,
                current_atr: float,
                current_date: pd.Timestamp,
                regime: str,
                config,
                current_high: float = None,
                adaptive_holding_period: int = None) -> tuple:
    """5 层止损检查

    优先级（从高到低）：
    1. CRASH 状态强制清仓
    2. 移动止盈（only-up）
    3. 分批止盈
    4. 时间止损
    5. 硬止损（仅 BULL）

    Args:
        adaptive_holding_period: spec §6.1 自适应持仓周期（None 用 config 默认）

    Returns:
        (should_sell, sell_ratio, reason)
    """
    # 1. CRASH 强制清仓
    if regime == "CRASH":
        if current_high is not None:
            position.update_highest(high=current_high, close=current_price)
        return True, 1.0, "CRASH 状态强制清仓"

    # 2. 移动止盈
    k_trail = config.atr_base_k.get(regime, 1.5)
    if current_atr > 0 and current_price > 0:
        realized_vol = current_atr / current_price * np.sqrt(252)
        if realized_vol > 0:
            vol_adj = np.clip(
                config.target_vol / max(realized_vol, 0.08),
                0.6, 1.5
            )
            k_trail *= vol_adj
    k_trail = float(np.clip(k_trail, config.atr_k_min, config.atr_k_max))

    new_trailing_stop = position.highest_price - k_trail * current_atr
    position.trailing_stop = max(
        getattr(position, "trailing_stop", -np.inf),
        new_trailing_stop
    )
    if current_price <= position.trailing_stop:
        if current_high is not None:
            position.update_highest(high=current_high, close=current_price)
        return True, 1.0, f"移动止盈 (k={k_trail:.2f})"

    # 3. 分批止盈
    profit = (current_price - position.entry_price) / position.entry_price
    batch_rules = config.partial_take_profit
    rules = batch_rules.get(regime)
    if rules is None:
        rules = batch_rules.get("BEAR", [])

    if rules:
        for level in rules:
            threshold = level["threshold"]
            ratio = level["ratio"]
            cumulative_ratio = sum(
                l["ratio"] for l in rules if l["threshold"] <= threshold
            )
            if profit >= threshold and position.partial_taken_pct < cumulative_ratio:
                # 修复：累加 partial_taken_pct 防止同一档重复触发
                position.partial_taken_pct = min(
                    position.partial_taken_pct + ratio, 1.0
                )
                position.partial_taken = position.partial_taken_pct >= 1.0
                if current_high is not None:
                    position.update_highest(high=current_high, close=current_price)
                return True, ratio, f"浮盈 {profit:.1%} >= {threshold:.0%}, 减 {ratio:.0%}"

    # 4. 时间止损
    days_held = int(np.busday_count(
        position.entry_date.date(), current_date.date()
    ))
    # spec §6.1 自适应持仓周期（None 时用 config 默认）
    if adaptive_holding_period is not None:
        max_period = adaptive_holding_period
    else:
        max_period = config.max_holding_days.get(regime, 20)
    if days_held >= max_period:  # ATOS10 fix: 无条件时间止损（不要求 profit<=0）
        if current_high is not None:
            position.update_highest(high=current_high, close=current_price)
        return True, 1.0, f"时间止损 ({days_held} 日, profit={profit:.2%})"

    # 5. 硬止损（仅 BULL）
    if regime == "BULL" and profit <= config.hard_stop_pct:
        if current_high is not None:
            position.update_highest(high=current_high, close=current_price)
        return True, 1.0, f"硬止损 {config.hard_stop_pct:.0%}"

    # 更新最高价
    if current_high is not None:
        position.update_highest(high=current_high, close=current_price)
    else:
        position.update_highest(high=current_price, close=current_price)

    return False, 0.0, "继续持有"
