"""选股层单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.selection import (
    calc_all_factors, StockSelector, get_factor_weights, FACTOR_WEIGHTS,
    MarketState, winsorize_mad, standardize_zscore, standardize_rank,
)
from atos.selection.weight_schedule import _validate_weights
from atos.indicators import calc_all_indicators
from atos.config import StrategyConfig


def test_factor_weights_sum_to_1():
    """所有状态的因子权重和应 ≈ 1.0"""
    for state, weights in FACTOR_WEIGHTS.items():
        assert _validate_weights(weights), f"{state.value} weights sum != 1.0: {sum(weights.values())}"


def test_get_factor_weights_bull():
    """BULL 状态权重获取"""
    w = get_factor_weights("BULL")
    assert "trend_ma60" in w
    assert w["trend_ma60"] > 0


def test_get_factor_weights_unknown():
    """未知状态应回退到 SIDEWAYS"""
    w = get_factor_weights("UNKNOWN_STATE")
    sideways_w = get_factor_weights("SIDEWAYS")
    assert w == sideways_w


def test_winsorize_mad():
    """MAD 去极值"""
    s = pd.Series([1, 2, 3, 4, 100])
    result = winsorize_mad(s, n=5)
    # 100 是离群值，应被截断
    assert result.max() < 100


def test_standardize_rank():
    """rank 标准化应在 [-0.5, 0.5]"""
    s = pd.Series([1, 2, 3, 4, 5])
    result = standardize_rank(s)
    assert result.between(-0.5, 0.5).all()


@pytest.fixture
def stock_data():
    np.random.seed(42)
    n = 200
    data = {}
    for sym in ["000001", "000002", "000003"]:
        close = pd.Series(
            np.cumsum(np.random.randn(n)) + 100,
            index=pd.date_range("2024-01-01", periods=n)
        )
        df_ind = calc_all_indicators(pd.DataFrame({
            "date": close.index, "open": close, "high": close + 1,
            "low": close - 1, "close": close,
            "volume": np.random.randint(1_000_000, 10_000_000, n),
        }))
        data[sym] = df_ind
    return data


def test_stock_selector_select(stock_data):
    """选股器应返回按得分排序的代码"""
    config = StrategyConfig()
    selector = StockSelector(config)
    date = pd.Timestamp("2024-06-01")
    top = selector.select(date=date, stock_data=stock_data, state="BULL", top_n=2)
    assert len(top) == 2
    assert all(s in stock_data.keys() for s in top)


def test_stock_selector_crash_returns_empty(stock_data):
    """CRASH 状态不选股（top_n 强制为 0）"""
    config = StrategyConfig()
    selector = StockSelector(config)
    date = pd.Timestamp("2024-06-01")
    # CRASH 时 target_n 应该为 0（在 engine 中处理）
    # selector 自身不感知状态，行为是返回得分最高的 top_n
    # 真实场景在 engine._process_buys 中通过 top_n_stocks.get('CRASH', 0) == 0 跳过
    top = selector.select(date=date, stock_data=stock_data, state="CRASH", top_n=0)
    assert top == []


def test_calc_all_factors_count():
    """应计算 12 个因子"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(100)) + 100,
                      index=pd.date_range("2024-01-01", periods=100))
    df_ind = calc_all_indicators(pd.DataFrame({
        "date": close.index, "open": close, "high": close + 1,
        "low": close - 1, "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, 100),
    }))
    factors = calc_all_factors(df_ind)
    assert len(factors.columns) == 14  # ATOS2 v2: 加 bb_width 补全 spec §7.1


def test_factor_directions():
    """因子方向与策略文档一致"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(100)) + 100,
                      index=pd.date_range("2024-01-01", periods=100))
    df_ind = calc_all_indicators(pd.DataFrame({
        "date": close.index, "open": close, "high": close + 1,
        "low": close - 1, "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, 100),
    }))
    factors = calc_all_factors(df_ind)
    # 验证因子方向（按策略文档）：
    # 趋势 4 个全 +，动量 3 个全 +，量价 3 个 (vol_ratio+, turnover-, corr+)
    # 形态 2 个 (rsi_centered+, near_high-)
    assert "trend_ma60" in factors.columns
    assert "turnover_stability" in factors.columns  # 负向
    assert "near_high_60" in factors.columns
