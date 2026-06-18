"""signals 模块"""
from .entry import (
    signal_ma_macd, signal_kdj_rsi, signal_boll_volume,
    signal_donchian_breakout, signal_macd_bottom_divergence,
    signal_ma_converge_break, generate_buy_signals,
)
from .exit import (
    signal_ma_macd_death, signal_kdj_overbought_death,
    signal_boll_mid_break, signal_macd_top_divergence,
    generate_sell_signals,
)
from .filter import BreakoutFilter
from .priority import SignalPriority


def generate_daily_signals(date, df, regime, positions, filter_mgr,
                            symbol=None, config=None) -> dict:
    """生成每日交易信号"""
    signals = {"buy": [], "sell": []}

    # 1. 假突破检查
    for sym, pos in positions.items():
        if pos.entry_date > date:
            continue
        try:
            current_low = df.loc[date, "low"]
        except KeyError:
            current_low = None
        if current_low is not None and pd.notna(current_low):
            if filter_mgr.check_filter(sym, date, current_low):
                signals["sell"].append((sym, 1.0, "假突破过滤"))

    # 2. 卖点信号
    sell_signals = generate_sell_signals(df)
    if sell_signals.loc[date, "any_sell"] == 1:
        for sym, pos in positions.items():
            if pos.entry_date <= date:
                signals["sell"].append((sym, 1.0, "技术卖点"))

    # 3. 买点信号
    buy_signals = generate_buy_signals(df, regime, config=config)
    if buy_signals.loc[date, "final"] == 1:
        if symbol is None and config is not None:
            symbol = config.symbol
        if symbol is not None:
            signals["buy"].append((symbol, "regime_signal"))

    return signals


import pandas as pd  # 末尾 import 避免循环

__all__ = [
    "signal_ma_macd", "signal_kdj_rsi", "signal_boll_volume",
    "signal_donchian_breakout", "signal_macd_bottom_divergence",
    "signal_ma_converge_break", "generate_buy_signals",
    "signal_ma_macd_death", "signal_kdj_overbought_death",
    "signal_boll_mid_break", "signal_macd_top_divergence",
    "generate_sell_signals",
    "BreakoutFilter", "SignalPriority", "generate_daily_signals",
]
