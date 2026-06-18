"""配置校验器"""
from typing import List


def validate_config(config) -> List[str]:
    """校验配置合法性"""
    errors = []

    for state, pos in config.base_position.items():
        if not 0 <= pos <= 1:
            errors.append(f"base_position[{state}] 必须在 [0, 1]")

    for state, k in config.atr_base_k.items():
        if not 0 < k <= 5:
            errors.append(f"atr_base_k[{state}] 必须在 (0, 5]")

    for fld in ["daily_loss_limit", "monthly_loss_limit",
                "quarterly_loss_limit", "yearly_loss_limit", "single_stock_loss_limit"]:
        v = getattr(config, fld, None)
        if v is not None and v > 0:
            errors.append(f"{fld} 应为负数或零（当前 {v}）")

    if not 0.5 <= config.market_breadth <= 1.0:
        errors.append(f"market_breadth {config.market_breadth} 不在 [0.5, 1.0]")

    if hasattr(config, "single_cap_max"):
        for state, cap in config.single_cap_max.items():
            if not 0 <= cap <= 1:
                errors.append(f"single_cap_max[{state}] {cap} 必须在 [0, 1]")

    if isinstance(config.top_n_stocks, dict):
        required = {"BULL", "SIDEWAYS", "BEAR", "CRASH", "CHOPPY_BEAR"}
        missing = required - set(config.top_n_stocks.keys())
        if missing:
            errors.append(f"top_n_stocks 缺少状态: {missing}")
        for state, n in config.top_n_stocks.items():
            if n < 0 or n > 50:
                errors.append(f"top_n_stocks[{state}] {n} 越界 [0, 50]")

    if getattr(config, "choppy_bear_grace_days", 3) < 0:
        errors.append("choppy_bear_grace_days 必须 >= 0")

    if hasattr(config, "open_threshold_by_regime"):
        for state, th in config.open_threshold_by_regime.items():
            if not 0 <= th <= 1:
                errors.append(f"open_threshold_by_regime[{state}] {th} 必须在 [0, 1]")

    if hasattr(config, "partial_take_profit"):
        for state, rules in config.partial_take_profit.items():
            if not isinstance(rules, list):
                errors.append(f"partial_take_profit[{state}] 必须是 list")
                continue
            for i, r in enumerate(rules):
                if not isinstance(r, dict):
                    errors.append(f"partial_take_profit[{state}][{i}] 必须是 dict")
                    continue
                if "threshold" not in r or "ratio" not in r:
                    errors.append(f"partial_take_profit[{state}][{i}] 缺 threshold/ratio")
                else:
                    if not 0 < r["threshold"] < 1:
                        errors.append(f"partial_take_profit[{state}][{i}].threshold 越界")
                    if not 0 < r["ratio"] <= 1:
                        errors.append(f"partial_take_profit[{state}][{i}].ratio 越界")

    return errors
