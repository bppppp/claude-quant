"""持仓类"""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class Position:
    """单个持仓的状态"""
    symbol: str
    entry_price: float
    entry_date: pd.Timestamp
    size: int
    entry_regime: str
    highest_price: float = 0.0
    highest_high: float = 0.0
    trailing_stop: float = field(default_factory=lambda: -np.inf)
    partial_taken: bool = False
    partial_taken_pct: float = 0.0
    atr_at_entry: float = 0.0
    trade_id: str = ""

    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.highest_high == 0.0:
            self.highest_high = self.entry_price
        if self.trailing_stop is None:
            self.trailing_stop = -np.inf
        if not isinstance(self.entry_date, pd.Timestamp):
            self.entry_date = pd.Timestamp(self.entry_date)

    def update_highest(self, high: float, close: float = None):
        if high > self.highest_high:
            self.highest_high = high
        if close is not None and close > self.highest_price:
            self.highest_price = close

    def holding_days(self, current_date: pd.Timestamp = None) -> int:
        if current_date is None:
            current_date = pd.Timestamp.now()
        return int(np.busday_count(self.entry_date.date(), current_date.date()))


class PositionManager:
    def __init__(self):
        self.positions: dict = {}

    def add(self, position: Position):
        self.positions[position.symbol] = position

    def remove(self, symbol: str, sell_ratio: float = 1.0) -> Optional[Position]:
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        if sell_ratio >= 1.0:
            del self.positions[symbol]
            return pos
        pos.size = int(pos.size * (1 - sell_ratio))
        pos.partial_taken = True
        pos.partial_taken_pct += sell_ratio
        return None

    def update_prices(self, prices: dict):
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_highest(price)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)
