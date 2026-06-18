"""状态层单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.regime import (
    detect_market_regime, apply_hysteresis, apply_hysteresis_with_crash_override,
    detect_choppy_bear, detect_choppy_bear_vectorized,
    compute_combined_regime, detect_full_regime,
)
from atos.indicators import calc_all_indicators


def _make_bull_df(n=250):
    """构造牛市：close 单调上升"""
    np.random.seed(42)
    close = pd.Series(
        np.cumsum(np.abs(np.random.randn(n)) * 0.5) + 100,
        index=pd.date_range("2023-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 10_000_000, n),
    })


def _make_bear_df(n=250):
    """构造熊市：close 单调下降"""
    np.random.seed(42)
    close = pd.Series(
        200 - np.cumsum(np.abs(np.random.randn(n)) * 0.5),
        index=pd.date_range("2023-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 10_000_000, n),
    })


def _make_choppy_bear_df(n=250):
    """构造震荡下行：缓慢阴跌 + 低波"""
    np.random.seed(42)
    close = pd.Series(
        100 - np.linspace(0, 15, n) + np.random.randn(n) * 0.3,
        index=pd.date_range("2023-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 5_000_000, n),
    })


def test_bull_state_detected():
    """牛市应被识别为 BULL"""
    df = _make_bull_df()
    df = calc_all_indicators(df)
    result = detect_market_regime(df)
    assert "BULL" in result["state"].values


def test_bear_state_detected():
    """熊市应被识别为 BEAR"""
    df = _make_bear_df()
    df = calc_all_indicators(df)
    result = detect_market_regime(df)
    assert "BEAR" in result["state"].values


def test_crash_or_trigger_5d():
    """5日跌幅 >= 8% 触发 CRASH"""
    np.random.seed(42)
    n = 30
    close = pd.Series(
        [100] * 5 + [90] * 5 + [85] * 5 + [80] * 15,
        index=pd.date_range("2023-01-01", periods=n)
    )
    df = pd.DataFrame({
        "open": close, "high": close, "low": close,
        "close": close, "volume": [1_000_000] * n,
    })
    df = calc_all_indicators(df)
    result = detect_market_regime(df)
    # 在 80 附近应触发 CRASH
    assert "CRASH" in result["state"].values


def test_crash_or_trigger_20d():
    """20日跌幅 >= 15% 触发 CRASH"""
    np.random.seed(42)
    n = 60
    prices = [100] * 20 + [85] * 40
    close = pd.Series(prices, index=pd.date_range("2023-01-01", periods=n))
    df = pd.DataFrame({
        "open": close, "high": close, "low": close,
        "close": close, "volume": [1_000_000] * n,
    })
    df = calc_all_indicators(df)
    result = detect_market_regime(df)
    assert "CRASH" in result["state"].values


def test_hysteresis_prevents_frequent_switch():
    """迟滞应防止频繁切换"""
    states = pd.Series(["BULL"] * 5 + ["SIDEWAYS"] * 3 + ["BULL"] * 5,
                        index=pd.date_range("2023-01-01", periods=13))
    result = apply_hysteresis(states, min_duration=3, cooldown=5)
    switch_count = (result != result.shift(1)).sum()
    assert switch_count <= 2


def test_crash_override_immediate():
    """CRASH 应立即响应（不等待迟滞）"""
    states = pd.Series(["BULL"] * 5 + ["CRASH"] + ["BULL"] * 5,
                        index=pd.date_range("2023-01-01", periods=11))
    result = apply_hysteresis_with_crash_override(states, min_duration=3, cooldown=5)
    assert result.iloc[5] == "CRASH"


def test_choppy_bear_vectorized():
    """向量化震荡下行检测"""
    df = _make_choppy_bear_df()
    df = calc_all_indicators(df)
    cb = detect_choppy_bear_vectorized(df, score_threshold=3)
    assert isinstance(cb, pd.Series)
    assert cb.dtype == bool


def test_combined_regime_choppy_bear_overlay():
    """choppy_bear 叠加应产生 CHOPPY_BEAR 状态"""
    regime_state = pd.Series(["BEAR"] * 20, index=pd.date_range("2023-01-01", periods=20))
    choppy_bear = pd.Series([False] * 5 + [True] * 10 + [False] * 5, index=regime_state.index)
    combined = compute_combined_regime(regime_state, choppy_bear, choppy_bear_grace_days=3)
    # 在 choppy_bear=True 的位置应变为 CHOPPY_BEAR
    choppy_mask = combined["effective_state"] == "CHOPPY_BEAR"
    assert choppy_mask.sum() >= 10


def test_combined_regime_target_position():
    """目标仓位应随状态变化"""
    regime_state = pd.Series(["BULL"] * 5 + ["BEAR"] * 5, index=pd.date_range("2023-01-01", periods=10))
    choppy_bear = pd.Series([False] * 10, index=regime_state.index)
    combined = compute_combined_regime(regime_state, choppy_bear)
    # BULL 应有较高目标仓位
    bull_pos = combined.loc[combined["state"] == "BULL", "target_position"].iloc[0]
    bear_pos = combined.loc[combined["state"] == "BEAR", "target_position"].iloc[0]
    assert bull_pos > bear_pos
    assert bull_pos > 0.5
    assert bear_pos < 0.3


def test_full_regime_pipeline():
    """完整 4 状态 + 震荡下行流程"""
    df = _make_bull_df()
    df = calc_all_indicators(df)
    result = detect_full_regime(df)
    assert "state" in result.columns
    assert "effective_state" in result.columns
    assert "target_position" in result.columns
    # 牛市大部分应为 BULL
    bull_pct = (result["state"] == "BULL").mean()
    assert bull_pct > 0.3
