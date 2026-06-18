"""P0/P1 修复验证测试"""
import numpy as np
import pandas as pd
import pytest

from atos.risk.stop_loss import check_exit
from atos.risk.adaptive import AdaptiveTracker
from atos.risk.position import Position
from atos.config import StrategyConfig
from atos.selection.weight_schedule import (
    get_factor_weights, FACTOR_WEIGHTS,
    MOMENTUM_FACTORS, MEAN_REVERSION_FACTORS, LOW_VOL_QUALITY_FACTORS,
)


@pytest.fixture
def config():
    return StrategyConfig()


def test_partial_take_profit_progressive_bull(config):
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    pos.partial_taken_pct = 0.0
    pos.highest_price = 10.8
    pos.highest_high = 10.8
    check_exit(pos, 10.8, 0.3, pd.Timestamp("2024-01-15"), "BULL", config)
    assert abs(pos.partial_taken_pct - 0.33) < 1e-6
    pos.highest_price = 11.6
    pos.highest_high = 11.6
    should_sell, ratio, reason = check_exit(
        pos, 11.6, 0.3, pd.Timestamp("2024-01-20"), "BULL", config
    )
    if should_sell:
        assert ratio == 0.5
        assert abs(pos.partial_taken_pct - 0.83) < 1e-6


def test_partial_take_profit_no_repeat(config):
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL",
                    highest_price=10.8, highest_high=10.8)
    pos.partial_taken_pct = 0.0
    should_sell, ratio, reason = check_exit(
        pos, 10.8, 0.3, pd.Timestamp("2024-01-15"), "BULL", config
    )
    assert should_sell == True
    assert ratio == 0.33
    assert abs(pos.partial_taken_pct - 0.33) < 1e-6
    pos.size = 67
    pos.highest_price = 10.85
    pos.highest_high = 10.85
    should_sell2, ratio2, reason2 = check_exit(
        pos, 10.85, 0.3, pd.Timestamp("2024-01-16"), "BULL", config
    )
    if should_sell2 and ratio2 > 0:
        assert not (ratio2 == 0.33 and "8%" in reason2)


def test_adaptive_holding_period_default(config):
    tracker = AdaptiveTracker(config, market_df=None)
    assert tracker.get_adaptive_holding_period("BULL") == 20
    assert tracker.get_adaptive_holding_period("SIDEWAYS") == 10
    assert tracker.get_adaptive_holding_period("BEAR") == 5


def test_adaptive_holding_period_extend(config):
    tracker = AdaptiveTracker(config, market_df=None)
    for i in range(15):
        tracker.record_trade(0.05, pd.Timestamp("2024-01-01"))
    assert tracker.rolling_winrate > 0.6
    assert tracker.get_adaptive_holding_period("BULL") == 22


def test_adaptive_holding_period_shorten(config):
    tracker = AdaptiveTracker(config, market_df=None)
    for i in range(15):
        tracker.record_trade(-0.05, pd.Timestamp("2024-01-01"))
    assert tracker.rolling_winrate < 0.45
    assert tracker.get_adaptive_holding_period("BULL") == 18
    assert tracker.get_adaptive_holding_period("BEAR") == 3
    assert tracker.get_adaptive_holding_period("CRASH") == 1


def test_adaptive_open_threshold_high_winrate(config):
    tracker = AdaptiveTracker(config, market_df=None)
    for i in range(15):
        tracker.record_trade(0.05, pd.Timestamp("2024-01-01"))
    th = tracker.get_adaptive_open_threshold("BULL")
    assert abs(th - 0.55) < 1e-6


def test_adaptive_open_threshold_low_winrate(config):
    tracker = AdaptiveTracker(config, market_df=None)
    for i in range(15):
        tracker.record_trade(-0.05, pd.Timestamp("2024-01-01"))
    th = tracker.get_adaptive_open_threshold("BULL")
    assert abs(th - 0.85) < 1e-6


def test_adaptive_open_threshold_neutral(config):
    tracker = AdaptiveTracker(config, market_df=None)
    for i in range(10):
        tracker.record_trade(0.05, pd.Timestamp("2024-01-01"))
    for i in range(10):
        tracker.record_trade(-0.05, pd.Timestamp("2024-01-01"))
    th = tracker.get_adaptive_open_threshold("BULL")
    assert abs(th - 0.70) < 1e-6


def test_weight_bull_momentum_emphasis():
    w = get_factor_weights("BULL")
    w_side = get_factor_weights("SIDEWAYS")
    assert w["ret_20d"] > w_side["ret_20d"]
    assert w["ret_60d"] > w_side["ret_60d"]
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_weight_sideways_mean_reversion_emphasis():
    w = get_factor_weights("SIDEWAYS")
    w_bull = get_factor_weights("BULL")
    for f in MEAN_REVERSION_FACTORS:
        if f in w and f in w_bull:
            assert w[f] >= w_bull[f] * 0.9
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_weight_bear_low_vol_quality_emphasis():
    w = get_factor_weights("BEAR")
    assert w["sharpe_60d"] > 0.10
    assert w["turnover_stability"] > 0.10
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_weight_factor_weights_dict_consistent():
    for state in ["BULL", "SIDEWAYS", "BEAR", "CRASH", "CHOPPY_BEAR"]:
        w1 = get_factor_weights(state)
        w2 = FACTOR_WEIGHTS[state]
        assert set(w1.keys()) == set(w2.keys())
        for k in w1:
            assert abs(w1[k] - w2[k]) < 1e-9


def test_check_exit_adaptive_holding(config):
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL",
                    highest_price=10.0, highest_high=10.0)
    days = int(np.busday_count(pos.entry_date.date(),
                                pd.Timestamp("2024-02-15").date()))
    should_sell, ratio, reason = check_exit(
        pos, 10.0, 0.3, pd.Timestamp("2024-02-15"),
        "BULL", config, adaptive_holding_period=10
    )
    if days > 10:
        assert should_sell == True
        assert "时间止损" in reason


def test_sell_pending_sell_orders(config):
    from atos.backtest.engine import BacktestEngine
    engine = BacktestEngine(config)
    engine._pending_sell_orders = {}
    engine.positions = {
        "000001": Position("000001", 10.0, pd.Timestamp("2024-01-01"),
                           100, "BULL", highest_price=10.0, highest_high=10.0)
    }
    engine.cash = 1_000_000
    engine.trades = []
    engine.adaptive = AdaptiveTracker(config, market_df=None)
    dates = pd.bdate_range("2024-01-15", "2024-01-20")
    pos = engine.positions["000001"]
    pos.trailing_stop = 10.5
    engine._process_sells(dates[0], {"000001": 10.5}, "BULL", 0.3, 10.5)
    assert engine.cash == 1_000_000
    assert dates[1] in engine._pending_sell_orders
    pending = engine._pending_sell_orders[dates[1]]
    assert len(pending) == 1
    symbol, ratio, reason = pending[0]
    assert symbol == "000001"
