"""ATOS2 v2 单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.regime.market_regime import detect_market_regime
from atos.indicators import calc_all_indicators
from atos.risk.adaptive import AdaptiveTracker
from atos.risk.breadth import compute_hs300_breadth_series
from atos.config import StrategyConfig


def test_bull_with_adx():
    """BULL 状态在 ADX 满足时识别（v2 新增第 6 条件）"""
    np.random.seed(42)
    n = 250
    close = pd.Series(
        np.cumsum(np.abs(np.random.randn(n)) * 0.5) + 100,
        index=pd.date_range("2023-01-01", periods=n)
    )
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 10_000_000, n),
    })
    df = calc_all_indicators(df)

    # 关闭 ADX（向后兼容）
    result_off = detect_market_regime(df, adx_bull_th=0.0)
    # 开启 ADX
    result_on = detect_market_regime(df, adx_bull_th=0.4)
    # 开启严格 ADX
    result_strict = detect_market_regime(df, adx_bull_th=0.6)
    # 开启严格应 <= 关闭
    assert (result_strict["state"] == "BULL").sum() <= (result_off["state"] == "BULL").sum()


def test_bear_with_rsi():
    """BEAR 状态在 RSI 满足时识别（v2 新增第 4 条件）"""
    np.random.seed(42)
    n = 250
    close = pd.Series(
        200 - np.cumsum(np.abs(np.random.randn(n)) * 0.5),
        index=pd.date_range("2023-01-01", periods=n)
    )
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 10_000_000, n),
    })
    df = calc_all_indicators(df)
    result_off = detect_market_regime(df, rsi_bear_th=100.0)
    result_on = detect_market_regime(df, rsi_bear_th=50.0)
    # 开启严格 RSI 应 <= 关闭
    assert (result_on["state"] == "BEAR").sum() <= (result_off["state"] == "BEAR").sum()


def test_adaptive_kelly_high_winrate():
    """胜率≥60% 时 Kelly 乘数 = base × adaptive_high"""
    config = StrategyConfig(
        kelly_multiplier=0.4,
        adaptive_kelly_enabled=True,
        kelly_adaptive_high=1.5,
        kelly_adaptive_low=0.5,
    )
    tracker = AdaptiveTracker(config, market_df=None, window=20)
    # 注入 20 笔全部盈利
    for i in range(20):
        tracker.record_trade(0.05, pd.Timestamp("2024-01-01") + pd.Timedelta(days=i))
    assert tracker.rolling_winrate == 1.0
    assert tracker.get_adaptive_kelly_multiplier() == min(0.4 * 1.5, 1.0)


def test_adaptive_kelly_low_winrate():
    """胜率<40% 时 Kelly 乘数 = base × adaptive_low"""
    config = StrategyConfig(
        kelly_multiplier=0.4,
        adaptive_kelly_enabled=True,
        kelly_adaptive_high=1.5,
        kelly_adaptive_low=0.5,
    )
    tracker = AdaptiveTracker(config, market_df=None, window=20)
    # 注入 20 笔：5 盈 15 亏
    for i in range(5):
        tracker.record_trade(0.05, pd.Timestamp("2024-01-01") + pd.Timedelta(days=i))
    for i in range(5, 20):
        tracker.record_trade(-0.05, pd.Timestamp("2024-01-01") + pd.Timedelta(days=i))
    assert tracker.rolling_winrate == 0.25
    assert tracker.get_adaptive_kelly_multiplier() == max(0.4 * 0.5, 0.1)


def test_adaptive_kelly_disabled():
    """关闭 adaptive 时直接返回 base"""
    config = StrategyConfig(
        kelly_multiplier=0.4,
        adaptive_kelly_enabled=False,
    )
    tracker = AdaptiveTracker(config, market_df=None, window=20)
    tracker.record_trade(0.05, pd.Timestamp("2024-01-01"))
    assert tracker.get_adaptive_kelly_multiplier() == 0.4


def test_adaptive_kelly_disabled_when_base_zero():
    """base=0 时直接返回 0"""
    config = StrategyConfig(
        kelly_multiplier=0.0,
        adaptive_kelly_enabled=True,
    )
    tracker = AdaptiveTracker(config, market_df=None, window=20)
    assert tracker.get_adaptive_kelly_multiplier() == 0.0
