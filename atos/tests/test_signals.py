"""信号层单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.signals.entry import (
    signal_ma_macd, signal_kdj_rsi, signal_boll_volume,
    signal_donchian_breakout, signal_macd_bottom_divergence,
    signal_ma_converge_break, generate_buy_signals,
)
from atos.signals.exit import (
    signal_ma_macd_death, signal_kdj_overbought_death,
    signal_boll_mid_break, signal_macd_top_divergence,
    generate_sell_signals,
)
from atos.signals.filter import BreakoutFilter
from atos.indicators import calc_all_indicators


@pytest.fixture
def sample_indicator_df():
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100,
                      index=pd.date_range("2024-01-01", periods=n))
    return calc_all_indicators(pd.DataFrame({
        "date": close.index, "open": close, "high": close + 1,
        "low": close - 1, "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    }))


def test_signal_ma_macd_returns_01(sample_indicator_df):
    """MA 金叉信号应为 0/1"""
    sig = signal_ma_macd(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}
    assert sig.sum() > 0  # 200 天至少有一些金叉


def test_signal_kdj_rsi_returns_01(sample_indicator_df):
    """KDJ+RSI 信号应为 0/1"""
    sig = signal_kdj_rsi(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}


def test_signal_boll_volume_uses_prev_low(sample_indicator_df):
    """BOLL_VOL 信号应用昨日 < 下轨 + 今日 > 下轨"""
    sig = signal_boll_volume(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}


def test_signal_donchian_breakout(sample_indicator_df):
    """Donchian 突破信号"""
    sig = signal_donchian_breakout(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}


def test_signal_macd_bottom_divergence(sample_indicator_df):
    """MACD 底背离"""
    sig = signal_macd_bottom_divergence(sample_indicator_df, lookback=60)
    assert set(sig.unique()) <= {0, 1}


def test_signal_ma_converge_break(sample_indicator_df):
    """均线粘合突破"""
    sig = signal_ma_converge_break(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}


def test_signal_ma_macd_death(sample_indicator_df):
    """MA 死叉"""
    sig = signal_ma_macd_death(sample_indicator_df)
    assert set(sig.unique()) <= {0, 1}


def test_generate_buy_signals_bull(sample_indicator_df):
    """BULL 状态买点信号"""
    signals = generate_buy_signals(sample_indicator_df, "BULL")
    assert "weighted_score" in signals.columns
    assert "final" in signals.columns
    # CRASH 状态应为 0
    signals_crash = generate_buy_signals(sample_indicator_df, "CRASH")
    assert signals_crash["final"].sum() == 0


def test_generate_sell_signals(sample_indicator_df):
    """卖点信号"""
    signals = generate_sell_signals(sample_indicator_df)
    assert "any_sell" in signals.columns
    assert set(signals["any_sell"].unique()) <= {0, 1}


def test_breakout_filter_no_record():
    """无记录时 check_filter 应返回 False"""
    f = BreakoutFilter()
    assert f.check_filter("000001", pd.Timestamp("2024-01-01"), 10.0) == False


def test_breakout_filter_buy_record():
    """买入后跌破触发假突破"""
    f = BreakoutFilter(holding_days=3)
    f.record_buy("000001", pd.Timestamp("2024-01-01"), 10.0)
    # 当日最低价 = 10.0, 不跌破
    assert f.check_filter("000001", pd.Timestamp("2024-01-02"), 10.0) == False
    # 跌破 9.5
    assert f.check_filter("000001", pd.Timestamp("2024-01-02"), 9.5) == True


def test_breakout_filter_expiry():
    """过期不再触发"""
    f = BreakoutFilter(holding_days=3)
    f.record_buy("000001", pd.Timestamp("2024-01-01"), 10.0)
    # 10 天后（过期）
    assert f.check_filter("000001", pd.Timestamp("2024-01-15"), 5.0) == False
