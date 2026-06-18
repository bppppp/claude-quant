"""backtest 模块"""
from .engine import BacktestEngine, BacktestResult
from .metrics import compute_all_metrics, compute_trade_metrics
from .walk_forward import walk_forward
from .perturbation import parameter_perturbation
from .report import generate_report
from .mr_v2 import backtest_v2


__all__ = [
    "BacktestEngine", "BacktestResult",
    "compute_all_metrics", "compute_trade_metrics",
    "walk_forward", "parameter_perturbation",
    "generate_report",
    "backtest_v2",
]
