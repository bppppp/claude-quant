"""ATOS10 v1: standalone mean reversion backtester"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict
from pathlib import Path

@dataclass
class Position:
    symbol: str
    entry_date: object
    entry_price: float
    shares: int

def safe_col(df, col):
    val = df[col]
    if isinstance(val, pd.DataFrame):
        return val.iloc[:, 0]
    return val

def detect_crash(bench):
    c = bench["close"]
    dd5 = c / c.shift(5) - 1
    dd20 = c / c.shift(20) - 1
    crash = ((dd5 <= -0.04) | (dd20 <= -0.10)).fillna(False)
    return crash

def backtest(start="2018-01-01", end="2022-12-31", rsi_th=35.0, max_pos=10, hold=3, stop_loss=-0.03, take_profit=0.05):
    from atos.data.universe import get_universe
    syms = get_universe("ALL")
    bench = pd.read_parquet("data/processed/v1/market/hs300.parquet")
    crash = detect_crash(bench)
    cash = 1_000_000.0
    positions = {}
    trades = []
    equity = []
    dates = sorted(bench["date"])
    dates = [d for d in dates if str(d)[:10] >= start and str(d)[:10] <= end]
    for i, date in enumerate(dates):
        if i % 50 == 0:
            print(".", end="", flush=True)
        # crash check
        crash_mask = crash[crash.index <= date]
        in_cooldown = False
        if len(crash_mask) > 0 and crash_mask.iloc[-1]:
            in_cooldown = True
        # exit
        to_remove = []
        for sym, pos in list(positions.items()):
            f = Path("data/processed/v1/stock") / f"{sym}.parquet"
            if not f.exists():
                continue
            df = pd.read_parquet(f)
            if date not in df.index:
                continue
            px = float(safe_col(df, "close").loc[date])
            ret = px / pos.entry_price - 1
            days = (pd.Timestamp(date) - pos.entry_date).days
            if ret >= take_profit or ret <= stop_loss or days >= hold or i == len(dates)-1:
                cash += px * pos.shares * (1 - 0.00125)
                trades.append({"ret": ret, "days": days})
                to_remove.append(sym)
        for sym in to_remove:
            del positions[sym]
        # enter
        if not in_cooldown and len(positions) < max_pos:
            cands = []
            for sym in syms:
                if sym in positions:
                    continue
                f = Path("data/processed/v1/stock") / f"{sym}.parquet"
                if not f.exists():
                    continue
                df = pd.read_parquet(f)
                if date not in df.index or "RSI6" not in df.columns:
                    continue
                rsi = safe_col(df, "RSI6")
                if date in rsi.index:
                    v = float(rsi.loc[date])
                    if not np.isnan(v) and v < rsi_th:
                        px = float(safe_col(df, "close").loc[date])
                        cands.append((sym, v, px))
            cands.sort(key=lambda x: x[1])
            n = max_pos - len(positions)
            for sym, _, px in cands[:n]:
                per = cash * 0.95 / max(n, 1)
                sh = int(per / px / 100) * 100
                if sh < 100:
                    continue
                cost = sh * px * 1.00025
                if cost <= cash:
                    cash -= cost
                    positions[sym] = Position(sym, pd.Timestamp(date), px, sh)
        # equity
        total = cash
        for sym, pos in positions.items():
            f = Path("data/processed/v1/stock") / f"{sym}.parquet"
            if f.exists():
                df = pd.read_parquet(f)
                if date in df.index:
                    total += float(safe_col(df, "close").loc[date]) * pos.shares
        equity.append({"date": date, "equity": total})
    eq = pd.DataFrame(equity).set_index("date")
    tot = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
    yrs = (eq.index[-1] - eq.index[0]).days / 365
    ann = (1 + tot) ** (1/yrs) - 1
    cummax = eq["equity"].cummax()
    dd = ((eq["equity"] - cummax) / cummax).min()
    wr = sum(1 for t in trades if t["ret"] > 0) / len(trades) if trades else 0
    return {"annual": ann, "total": tot, "max_dd": dd, "n_trades": len(trades), "win_rate": wr}

if __name__ == "__main__":
    r = backtest()
    print()
    print("=== ATOS10 v1 ===")
    print(f"年化: {r["annual"]*100:+.2f}%")
    print(f"累计: {r["total"]*100:+.2f}%")
    print(f"最大回撤: {r["max_dd"]*100:+.2f}%")
    print(f"笔数: {r["n_trades"]}")
    print(f"胜率: {r["win_rate"]*100:.1f}%")