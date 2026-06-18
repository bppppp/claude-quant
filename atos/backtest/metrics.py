"""绩效指标"""
import numpy as np
import pandas as pd


def compute_max_drawdown_duration(equity: pd.Series) -> int:
    cummax = equity.cummax()
    is_drawdown = equity < cummax
    if not is_drawdown.any():
        return 0
    groups = (is_drawdown != is_drawdown.shift()).cumsum()
    return int(is_drawdown.groupby(groups).sum().max())


def compute_omega(returns: pd.Series, threshold: float = 0) -> float:
    excess = returns - threshold
    gain = excess[excess > 0].sum()
    loss = -excess[excess < 0].sum()
    if loss == 0:
        return 999.0
    return gain / loss


def compute_rolling_sharpe(returns: pd.Series, window: int = 252) -> pd.Series:
    rolling_mean = returns.rolling(window).mean() * 252
    rolling_std = returns.rolling(window).std() * np.sqrt(252)
    return rolling_mean / rolling_std.replace(0, np.nan)


def compute_max_consecutive(series: pd.Series) -> int:
    if series.empty:
        return 0
    groups = (series != series.shift()).cumsum()
    return int(series.groupby(groups).sum().max())


def compute_all_metrics(equity_curve: pd.Series, trades: pd.DataFrame = None) -> dict:
    """计算完整绩效指标"""
    metrics = {}

    n_days = len(equity_curve)
    if n_days < 2:
        return {
            "total_return": 0, "annual_return": 0, "n_years": 0,
            "volatility": 0, "max_drawdown": 0, "sharpe": 0,
        }

    n_years = n_days / 252
    first_eq = float(equity_curve.iloc[0])
    if first_eq <= 0 or pd.isna(first_eq):
        total_return = 0.0
    else:
        total_return = float(equity_curve.iloc[-1] / first_eq - 1)

    annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0
    metrics["total_return"] = total_return
    metrics["annual_return"] = annual_return
    metrics["n_years"] = n_years

    daily_ret = equity_curve.pct_change().dropna()
    if len(daily_ret) == 0:
        metrics.update({
            "volatility": 0, "downside_vol": 0, "max_drawdown": 0,
            "var_95": 0, "cvar_95": 0, "sharpe": 0,
            "sortino": 0, "calmar": 0, "omega": 0,
            "monthly_win_rate": 0, "quarterly_win_rate": 0, "monthly_vol": 0,
        })
    else:
        metrics["volatility"] = float(daily_ret.std() * np.sqrt(252))
        down_ret = daily_ret[daily_ret < 0]
        metrics["downside_vol"] = float(down_ret.std() * np.sqrt(252)) if len(down_ret) > 0 else 0
        dd = equity_curve / equity_curve.cummax() - 1
        metrics["max_drawdown"] = float(dd.min())
        metrics["drawdown_duration"] = compute_max_drawdown_duration(equity_curve)
        metrics["var_95"] = float(-daily_ret.quantile(0.05))
        cvar = -daily_ret[daily_ret <= daily_ret.quantile(0.05)].mean()
        metrics["cvar_95"] = float(cvar) if not pd.isna(cvar) else 0

        rf = 0.025
        excess = annual_return - rf
        metrics["sharpe"] = float(excess / metrics["volatility"]) if metrics["volatility"] > 0 else 0
        metrics["sortino"] = float(excess / metrics["downside_vol"]) if metrics["downside_vol"] > 0 else 0
        metrics["calmar"] = float(annual_return / abs(metrics["max_drawdown"])) if metrics["max_drawdown"] < 0 else 0
        metrics["omega"] = float(compute_omega(daily_ret, 0))

        monthly = equity_curve.resample("ME").last().pct_change().dropna()
        quarterly = equity_curve.resample("QE").last().pct_change().dropna()
        metrics["monthly_win_rate"] = float((monthly > 0).mean()) if len(monthly) > 0 else 0
        metrics["quarterly_win_rate"] = float((quarterly > 0).mean()) if len(quarterly) > 0 else 0
        metrics["monthly_vol"] = float(monthly.std()) if len(monthly) > 0 else 0

    if trades is not None and not trades.empty:
        metrics.update(compute_trade_metrics(trades))

    return metrics


def compute_trade_metrics(trades: pd.DataFrame) -> dict:
    """按 trade_id 配对的交易指标"""
    metrics = {
        "n_buys": int((trades["action"] == "BUY").sum()),
        "n_sells": int((trades["action"] == "SELL").sum()),
    }
    metrics["n_trades"] = min(metrics["n_buys"], metrics["n_sells"])

    if trades.empty or "trade_id" not in trades.columns:
        return metrics

    paired_list = []
    for trade_id, group in trades.groupby("trade_id"):
        buys = group[group["action"] == "BUY"]
        sells = group[group["action"] == "SELL"]
        if not buys.empty and not sells.empty:
            entry_price = (buys["price"] * buys["shares"]).sum() / buys["shares"].sum()
            exit_price = (sells["price"] * sells["shares"]).sum() / sells["shares"].sum()
            paired_list.append({
                "trade_id": trade_id,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "shares": min(buys["shares"].sum(), sells["shares"].sum()),
                "pnl": (exit_price / entry_price - 1) if entry_price > 0 else 0,
            })

    if not paired_list:
        return metrics

    paired = pd.DataFrame(paired_list)
    win = paired[paired["pnl"] > 0]
    loss = paired[paired["pnl"] <= 0]
    n = len(paired)
    metrics["win_rate"] = len(win) / n
    metrics["avg_pnl"] = float(paired["pnl"].mean())
    metrics["avg_win"] = float(win["pnl"].mean()) if not win.empty else 0
    metrics["avg_loss"] = float(loss["pnl"].mean()) if not loss.empty else 0
    if metrics["avg_loss"] != 0:
        metrics["profit_loss_ratio"] = abs(metrics["avg_win"] / metrics["avg_loss"])
    else:
        metrics["profit_loss_ratio"] = float("inf")
    metrics["max_consecutive_wins"] = compute_max_consecutive(paired["pnl"] > 0)
    metrics["max_consecutive_losses"] = compute_max_consecutive(paired["pnl"] <= 0)
    metrics["max_pnl"] = float(paired["pnl"].max())
    metrics["min_pnl"] = float(paired["pnl"].min())

    return metrics
