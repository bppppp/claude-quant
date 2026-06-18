"""代码与策略文档一致性测试

逐项核对 ATOS-des.md §3 (分状态参数表) 与 dev-docs §9 (config) 的实现。
"""
import pandas as pd
import numpy as np
import pytest

from atos.config import StrategyConfig
from atos.config.validator import validate_config


# ATOS-des.md §3 分状态参数表（注意：dev-docs 中 BULL 总仓位 = 0.85，与 1.0 略不同，
# 实际 dev-docs §9.4 / §7.2 / 7.3 均为 0.85，这是 v8.5 H2 修复后的实操值）
PARAM_TABLE = {
    "BULL": {
        "总仓位上限": 0.85,  # 实际 dev-docs 实现值
        "单只上限": 0.15,
        "持仓只数": 8,
        "硬止损": -0.08,
        "移动止盈 k": 3.0,
        "持仓周期": 20,
        "开仓信号阈值": 0.70,
    },
    "SIDEWAYS": {
        "总仓位上限": 0.55,  # dev-docs 默认 0.55 (在 §3 的 50-70% 区间内)
        "单只上限": 0.10,
        "持仓只数": 6,
        "硬止损": None,
        "移动止盈 k": 2.0,
        "持仓周期": 10,
        "开仓信号阈值": 0.60,
    },
    "BEAR": {
        "总仓位上限": 0.15,  # dev-docs YAML 默认值（在 ATOS-des.md 10-20% 区间内）
        "单只上限": 0.05,
        "持仓只数": 4,
        "硬止损": None,
        "移动止盈 k": 1.5,
        "持仓周期": 5,
        "开仓信号阈值": 0.75,
    },
    "CRASH": {
        "总仓位上限": 0.00,
        "硬止损": None,
        "移动止盈 k": 1.0,
        "持仓周期": 1,
    },
    "CHOPPY_BEAR": {
        "总仓位上限": 0.15,  # dev-docs YAML 默认值（与 BEAR 类似）
        "单只上限": 0.03,
        "持仓只数": 4,
        "持仓周期": 5,
        "开仓信号阈值": 0.75,
    },
}


def test_total_position_cap_matches_doc():
    """总仓位上限与 dev-docs §9.4 一致（注意：ATOS-des.md §3 写 1.0，
    但 dev-docs 实际实现为 0.85，这是修复 v8.5 H2 后的实操值）"""
    config = StrategyConfig()
    assert config.base_position["BULL"] == PARAM_TABLE["BULL"]["总仓位上限"]
    assert config.base_position["SIDEWAYS"] == PARAM_TABLE["SIDEWAYS"]["总仓位上限"]
    assert config.base_position["BEAR"] == PARAM_TABLE["BEAR"]["总仓位上限"]
    assert config.base_position["CRASH"] == PARAM_TABLE["CRASH"]["总仓位上限"]
    assert config.base_position["CHOPPY_BEAR"] == PARAM_TABLE["CHOPPY_BEAR"]["总仓位上限"]


def test_trailing_stop_k_matches_doc():
    """移动止盈 k 与策略文档 §3 一致"""
    config = StrategyConfig()
    assert config.atr_base_k["BULL"] == PARAM_TABLE["BULL"]["移动止盈 k"]
    assert config.atr_base_k["SIDEWAYS"] == PARAM_TABLE["SIDEWAYS"]["移动止盈 k"]
    assert config.atr_base_k["BEAR"] == PARAM_TABLE["BEAR"]["移动止盈 k"]
    assert config.atr_base_k["CHOPPY_BEAR"] == 1.5


def test_holding_period_matches_doc():
    """持仓周期与策略文档 §3 一致"""
    config = StrategyConfig()
    assert config.max_holding_days["BULL"] == PARAM_TABLE["BULL"]["持仓周期"]
    assert config.max_holding_days["SIDEWAYS"] == PARAM_TABLE["SIDEWAYS"]["持仓周期"]
    assert config.max_holding_days["BEAR"] == PARAM_TABLE["BEAR"]["持仓周期"]
    assert config.max_holding_days["CHOPPY_BEAR"] == PARAM_TABLE["CHOPPY_BEAR"]["持仓周期"]


def test_open_threshold_matches_doc():
    """开仓信号阈值与策略文档 §3 一致"""
    config = StrategyConfig()
    assert config.open_threshold_by_regime["BULL"] == PARAM_TABLE["BULL"]["开仓信号阈值"]
    assert config.open_threshold_by_regime["SIDEWAYS"] == PARAM_TABLE["SIDEWAYS"]["开仓信号阈值"]
    assert config.open_threshold_by_regime["BEAR"] == PARAM_TABLE["BEAR"]["开仓信号阈值"]
    assert config.open_threshold_by_regime["CHOPPY_BEAR"] == PARAM_TABLE["CHOPPY_BEAR"]["开仓信号阈值"]


def test_hard_stop_is_minus_8pct():
    """硬止损 = -8% 固定比例"""
    config = StrategyConfig()
    assert config.hard_stop_pct == -0.08


def test_single_cap_max_matches_doc():
    """单只上限与策略文档 §3 一致"""
    config = StrategyConfig()
    assert config.single_cap_max["BULL"] == 0.15
    assert config.single_cap_max["SIDEWAYS"] == 0.10
    assert config.single_cap_max["BEAR"] == 0.05
    assert config.single_cap_max["CHOPPY_BEAR"] == 0.03


def test_top_n_stocks_matches_doc():
    """持仓只数与策略文档 §3 一致"""
    config = StrategyConfig()
    assert config.top_n_stocks["BULL"] == 8
    assert config.top_n_stocks["SIDEWAYS"] == 6
    assert config.top_n_stocks["BEAR"] == 4
    assert config.top_n_stocks["CRASH"] == 0
    assert config.top_n_stocks["CHOPPY_BEAR"] == 4


def test_partial_take_profit_bull():
    """BULL 分批止盈: 8% 减 1/3 + 15% 减半"""
    config = StrategyConfig()
    bull_rules = config.partial_take_profit["BULL"]
    assert len(bull_rules) == 2
    assert bull_rules[0]["threshold"] == 0.08
    assert bull_rules[0]["ratio"] == 0.33
    assert bull_rules[1]["threshold"] == 0.15
    assert bull_rules[1]["ratio"] == 0.50


def test_partial_take_profit_bear():
    """BEAR 分批止盈: 3% 全走"""
    config = StrategyConfig()
    bear_rules = config.partial_take_profit["BEAR"]
    assert len(bear_rules) == 1
    assert bear_rules[0]["threshold"] == 0.03
    assert bear_rules[0]["ratio"] == 1.00


def test_money_management_limits():
    """资金管理限额为负数"""
    config = StrategyConfig()
    assert config.daily_loss_limit < 0
    assert config.monthly_loss_limit < 0
    assert config.quarterly_loss_limit < 0
    assert config.yearly_loss_limit < 0
    assert config.single_stock_loss_limit < 0
    assert abs(config.daily_loss_limit) == 0.02
    assert abs(config.monthly_loss_limit) == 0.05
    assert abs(config.quarterly_loss_limit) == 0.10
    assert abs(config.yearly_loss_limit) == 0.15
    assert abs(config.single_stock_loss_limit) == 0.03


def test_effective_single_cap_math():
    """effective_single_cap 数学一致性：cap × n <= total"""
    config = StrategyConfig()
    for state in ["BULL", "SIDEWAYS", "BEAR", "CHOPPY_BEAR"]:
        cap = config.effective_single_cap(state)
        n = config.top_n_stocks[state]
        total = config.base_position[state]
        assert cap * n <= total + 0.001, f"{state}: cap={cap} * n={n} > total={total}"


def test_atr_k_range():
    """ATR k 范围 [1.2, 4.0]"""
    config = StrategyConfig()
    assert config.atr_k_min == 1.2
    assert config.atr_k_max == 4.0


def test_cooldown_days_match():
    """冷却期：5 日（个股）"""
    from atos.risk import CooldownManager
    cd = CooldownManager()
    date = pd.Timestamp("2024-01-01")
    cd.record_exit("000001", date, is_failure=False)
    can, _ = cd.can_buy("000001", date + pd.tseries.offsets.BDay(4), "BULL")
    assert can == False
    can, _ = cd.can_buy("000001", date + pd.tseries.offsets.BDay(6), "BULL")
    assert can == True


def test_choppy_bear_grace_days():
    """CHOPPY_BEAR 延后撤销天数 = 3"""
    config = StrategyConfig()
    assert config.choppy_bear_grace_days == 3


def test_market_breadth_range():
    """market_breadth 范围 [0.5, 1.0]"""
    config = StrategyConfig()
    config.market_breadth = 0.3
    errors = validate_config(config)
    assert any("market_breadth" in e for e in errors)
    config.market_breadth = 1.0
    errors = validate_config(config)
    assert not any("market_breadth" in e for e in errors)


def test_state_classification_4_states():
    """状态层应支持 4 状态"""
    from atos.regime import detect_market_regime
    from atos.indicators import calc_all_indicators

    np.random.seed(42)
    n = 250
    close = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range("2024-01-01", periods=n)
    )
    df = calc_all_indicators(pd.DataFrame({
        "date": close.index, "open": close, "high": close + 1,
        "low": close - 1, "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }))
    result = detect_market_regime(df)
    valid_states = {"BULL", "SIDEWAYS", "BEAR", "CRASH"}
    assert set(result["state"].unique()) <= valid_states

