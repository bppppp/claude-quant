"""信号优先级"""


class SignalPriority:
    SELL_PRIORITY = [
        "crash_force_exit",
        "trailing_stop",
        "batch_take_profit",
        "time_stop",
        "hard_stop",
        "false_breakout",
        "sell_signal",
    ]

    BUY_PRIORITY = [
        "selected_by_regime",
        "regime_bull",
    ]

    @classmethod
    def should_sell_first(cls, signal1: str, signal2: str) -> str:
        p1 = cls.SELL_PRIORITY.index(signal1) if signal1 in cls.SELL_PRIORITY else 999
        p2 = cls.SELL_PRIORITY.index(signal2) if signal2 in cls.SELL_PRIORITY else 999
        return signal1 if p1 < p2 else signal2
