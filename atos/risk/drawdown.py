"""回撤阶梯"""
import pandas as pd


# 降序：先检查最严重的回撤
DD_STEPS_DESC = [
    (0.20, None,  "暂停策略"),
    (0.15, 0.00,  "空仓 5 日"),
    (0.10, 0.40,  "降至 40%"),
    (0.05, 0.70,  "降至 70%"),
]


def compute_current_drawdown(equity_curve: pd.Series) -> float:
    cummax = equity_curve.cummax()
    dd = (equity_curve - cummax) / cummax
    return float(dd.iloc[-1]) if len(dd) else 0.0


def apply_drawdown_step(current_dd: float, base_position: float = 1.0,
                          consecutive_days_below_threshold: int = 0) -> tuple:
    """应用回撤阶梯

    Returns:
        (target_position, reason, is_paused)
    """
    for dd_th, target_pos, desc in DD_STEPS_DESC:
        if current_dd <= -dd_th:
            if target_pos is None:
                return None, f"回撤 {abs(current_dd):.2%} >= 20%, {desc}", True
            return target_pos, f"回撤 {abs(current_dd):.2%} 触发, {desc}, 仓位 {target_pos:.0%}", False
    return base_position, "正常", False


class DrawdownTracker:
    def __init__(self, lookback_days: int = 252):
        self.lookback_days = lookback_days
        self.peak = 0.0
        self.current_dd = 0.0
        self.consecutive_low_days = 0
        self.pause_until = None

    def update(self, equity: float, current_date: pd.Timestamp) -> dict:
        if equity > self.peak:
            self.peak = equity
            self.consecutive_low_days = 0
        else:
            self.consecutive_low_days += 1

        self.current_dd = (equity - self.peak) / self.peak if self.peak > 0 else 0.0

        if self.pause_until and current_date < self.pause_until:
            return {
                "current_dd": self.current_dd,
                "target_position": 0,
                "is_paused": True,
                "reason": f"暂停至 {self.pause_until.date()}",
            }

        target_pos, reason, is_paused = apply_drawdown_step(self.current_dd, 1.0)

        if target_pos is None or is_paused:
            return {
                "current_dd": self.current_dd,
                "target_position": 0,
                "is_paused": True,
                "reason": reason,
            }

        # 15% 触发 5 日暂停
        if self.current_dd <= -0.15 and self.pause_until is None:
            self.pause_until = current_date + pd.tseries.offsets.BDay(5)

        return {
            "current_dd": self.current_dd,
            "target_position": target_pos,
            "is_paused": False,
            "reason": reason,
        }
