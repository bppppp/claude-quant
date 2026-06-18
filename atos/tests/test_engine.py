"""回测引擎单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.backtest import BacktestEngine, BacktestResult
from atos.backtest.metrics import compute_all_metrics, compute_trade_metrics
from atos.backtest.engine import BacktestEngine as BE
from atos.config import StrategyConfig


@pytest.fixture
def simple_market_df():
    """简单的市场数据"""
    np.random.seed(42)
    n = 100
    close = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range("2024-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1_000_000, 10_000_000, n),
        "MA20": close.rolling(20).mean(),
        "MA60": close.rolling(60).mean(),
        "ATR": pd.Series(1.0, index=close.index),
    })


def test_engine_init():
    """引擎初始化"""
    config = StrategyConfig()
    engine = BacktestEngine(config)
    assert engine.cash == config.initial_capital
    assert len(engine.positions) == 0
    assert engine.trades == []


def test_metrics_basic():
    """基础指标计算"""
    equity = pd.Series(
        [100, 101, 102, 101, 103, 105],
        index=pd.date_range("2024-01-01", periods=6)
    )
    metrics = compute_all_metrics(equity)
    assert "annual_return" in metrics
    assert "sharpe" in metrics
    assert "max_drawdown" in metrics


def test_metrics_with_trades():
    """含交易的指标"""
    equity = pd.Series(
        [100, 105, 110, 108, 112],
        index=pd.date_range("2024-01-01", periods=5)
    )
    trades = pd.DataFrame({
        "trade_id": ["t1", "t1", "t2", "t2", "t3", "t3"],
        "date": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-02",
                                 "2024-01-04", "2024-01-03", "2024-01-05"]),
        "action": ["BUY", "SELL", "BUY", "SELL", "BUY", "SELL"],
        "symbol": ["000001", "000001", "000002", "000002", "000003", "000003"],
        "price": [10.0, 11.0, 20.0, 19.0, 30.0, 33.0],
        "shares": [100, 100, 50, 50, 33, 33],
    })
    metrics = compute_all_metrics(equity, trades)
    assert "n_trades" in metrics
    assert "win_rate" in metrics
    assert metrics["win_rate"] > 0  # 至少有些盈利


def test_metrics_empty():
    """空数据应返回空字典"""
    equity = pd.Series(dtype=float)
    metrics = compute_all_metrics(equity)
    assert metrics["annual_return"] == 0
