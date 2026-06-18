"""Walk-Forward Analysis"""
import numpy as np
import pandas as pd

from .engine import BacktestEngine


def walk_forward(df: pd.DataFrame,
                  config,
                  train_years: int = 3,
                  test_years: int = 1,
                  step_years: int = 1) -> dict:
    """Walk-Forward 分析"""
    if len(df) == 0:
        raise ValueError("Empty dataframe")

    start_year = df.index.year.min()
    end_date = df.index.max()
    end_year = end_date.year

    folds = []
    fold_start = start_year

    while True:
        test_end_candidate = pd.Timestamp(f"{fold_start + train_years + test_years}-12-31")
        if test_end_candidate > end_date:
            break

        train_start = f"{fold_start}-01-01"
        train_end = f"{fold_start + train_years}-12-31"
        test_start = f"{fold_start + train_years}-01-01"
        test_end = min(test_end_candidate, end_date).strftime("%Y-%m-%d")

        full_context = df[train_start:test_end]
        engine = BacktestEngine(config)
        result = engine.run(full_context, test_only_period=(test_start, test_end))

        folds.append({
            "fold": len(folds) + 1,
            "train_period": (train_start, train_end),
            "test_period": (test_start, test_end),
            "annual_return": result.metrics.get("annual_return", 0),
            "sharpe": result.metrics.get("sharpe", 0),
            "max_drawdown": result.metrics.get("max_drawdown", 0),
        })

        fold_start += step_years

    if not folds:
        raise ValueError("Not enough data for walk-forward analysis")

    return {
        "folds": pd.DataFrame(folds),
        "summary": {
            "mean_annual_return": float(np.mean([f["annual_return"] for f in folds])),
            "mean_sharpe": float(np.mean([f["sharpe"] for f in folds])),
            "mean_max_dd": float(np.mean([f["max_drawdown"] for f in folds])),
        }
    }
