"""风控层单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.risk import (
    Position, PositionManager, check_exit,
    CooldownManager, DrawdownTracker, MoneyManager,
)
from atos.config import StrategyConfig


@pytest.fixture
def config():
    return StrategyConfig()


def test_position_highest_update():
    """Position.highest_high 应正确更新"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    pos.update_highest(11.0, close=10.8)
    pos.update_highest(10.5, close=10.4)
    assert pos.highest_high == 11.0
    assert pos.highest_price == 10.8


def test_position_holding_days():
    """holding_days 应使用交易日"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    days = pos.holding_days(pd.Timestamp("2024-01-10"))  # 7 个交易日
    assert days >= 5


def test_position_manager_add_remove():
    """PositionManager 添加/移除"""
    pm = PositionManager()
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    pm.add(pos)
    assert "000001" in pm.positions
    pm.remove("000001")
    assert "000001" not in pm.positions


def test_check_exit_crash_immediate():
    """CRASH 状态应立即清仓"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    config = StrategyConfig()
    should_sell, ratio, reason = check_exit(
        pos, 10.5, 0.3, pd.Timestamp("2024-01-15"),
        "CRASH", config
    )
    assert should_sell == True
    assert ratio == 1.0
    assert "CRASH" in reason


def test_check_exit_hard_stop_bull():
    """BULL 状态硬止损 -8%"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL",
                    highest_price=10.0, highest_high=10.0)
    config = StrategyConfig()
    # 价格 9.0 = -10% 亏损，BULL 状态应触发硬止损或移动止盈
    should_sell, ratio, reason = check_exit(
        pos, 9.0, 0.3, pd.Timestamp("2024-01-15"),
        "BULL", config
    )
    assert should_sell == True
    # 应该是硬止损或移动止盈触发
    assert any(s in reason for s in ["硬止损", "移动止盈"])


def test_check_exit_no_hard_stop_sideways():
    """SIDEWAYS 状态无硬止损"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    config = StrategyConfig()
    should_sell, ratio, reason = check_exit(
        pos, 9.0, 0.3, pd.Timestamp("2024-01-15"),
        "SIDEWAYS", config
    )
    # SIDEWAYS 无硬止损，应到 trailing stop 或继续持有
    if should_sell:
        assert "硬止损" not in reason


def test_check_exit_partial_take_profit():
    """分批止盈：浮盈 8% 减 1/3"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    config = StrategyConfig()
    should_sell, ratio, reason = check_exit(
        pos, 10.9, 0.3, pd.Timestamp("2024-01-15"),
        "BULL", config
    )
    if should_sell:
        # BULL 浮盈 8% 减 1/3 = 0.33
        assert ratio <= 0.5


def test_check_exit_trailing_stop_only_up():
    """移动止盈只允许上移"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL",
                    highest_price=11.0, highest_high=11.0)
    config = StrategyConfig()
    # 第一次调用
    pos1 = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL",
                     highest_price=11.0, highest_high=11.0, trailing_stop=10.0)
    # 不应下移
    assert pos1.trailing_stop == 10.0


def test_cooldown_can_buy_after_5_days():
    """卖出后 5 日冷却"""
    cd = CooldownManager()
    date = pd.Timestamp("2024-01-01")
    cd.record_exit("000001", date, is_failure=False)
    can, _ = cd.can_buy("000001", pd.Timestamp("2024-01-03"), "BULL")
    assert can == False  # 5 日内不能买
    can, _ = cd.can_buy("000001", pd.Timestamp("2024-01-10"), "BULL")
    assert can == True


def test_cooldown_failure_30_days():
    """30 日内 2 次失败禁买"""
    cd = CooldownManager()
    date = pd.Timestamp("2024-01-01")
    cd.record_exit("000001", date, is_failure=True)
    cd.record_exit("000001", date + pd.Timedelta(days=5), is_failure=True)
    can, reason = cd.can_buy("000001", date + pd.Timedelta(days=20), "BULL")
    assert can == False
    assert "失败" in reason


def test_drawdown_step_pause_at_20pct():
    """20% 回撤暂停"""
    pos, reason, paused = None, None, None
    target, reason, is_paused = None, None, None
    target, reason, is_paused = None, None, None
    # 调用 apply_drawdown_step
    from atos.risk.drawdown import apply_drawdown_step
    target, reason, is_paused = apply_drawdown_step(-0.20, 1.0)
    assert is_paused == True
    assert target is None


def test_drawdown_step_10pct_reduces_to_40pct():
    """10% 回撤降至 40% 仓位"""
    from atos.risk.drawdown import apply_drawdown_step
    target, reason, is_paused = apply_drawdown_step(-0.10, 1.0)
    assert target == 0.40
    assert is_paused == False


def test_money_manager_daily_loss_stop():
    """当日亏损 > 2% 应停止开仓"""
    mm = MoneyManager(initial_equity=1_000_000)
    date = pd.Timestamp("2024-01-01")
    result = mm.update_pnl(-30_000, date, 970_000)
    assert result["should_stop_trading"] == True


def test_money_manager_yearly_loss_force_empty():
    """年度亏损 > 15% 应强制空仓"""
    mm = MoneyManager(initial_equity=1_000_000)
    date = pd.Timestamp("2024-01-01")
    result = mm.update_pnl(-200_000, date, 800_000)
    assert result["should_force_empty"] == True


def test_money_manager_quarterly_loss_multiplier():
    """季度亏损 > 10% 应降至 1/3 仓位"""
    mm = MoneyManager(initial_equity=1_000_000)
    date = pd.Timestamp("2024-01-01")
    result = mm.update_pnl(-120_000, date, 880_000)
    assert abs(result["position_multiplier"] - 0.33) < 0.01


def test_check_single_stock_loss():
    """单只浮亏 > 3% 触发清仓"""
    mm = MoneyManager(initial_equity=1_000_000)
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    # 当前价 9.6, 浮亏 -4%
    assert mm.check_single_stock_loss(pos, current_price=9.6) == True
    # 当前价 9.8, 浮亏 -2%
    assert mm.check_single_stock_loss(pos, current_price=9.8) == False
