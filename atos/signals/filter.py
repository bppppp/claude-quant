"""假突破过滤器"""
import pandas as pd


class BreakoutFilter:
    """假突破过滤器：买入后 3 个交易日内跌破买入当天最低价 -> 强制平仓"""

    def __init__(self, holding_days: int = 3, trading_days=None):
        self.holding_days = holding_days
        self.trading_days = trading_days
        self.buy_records = {}

    def record_buy(self, symbol: str, date, low_price: float):
        expire_date = self._get_trading_date_after(date, self.holding_days)
        self.buy_records[symbol] = {
            "date": date,
            "buy_day_low": low_price,
            "expire_date": expire_date
        }

    def _get_trading_date_after(self, start_date, n_days: int):
        if self.trading_days is None or len(self.trading_days) == 0:
            return start_date + pd.tseries.offsets.BDay(n_days)
        future_days = [d for d in self.trading_days if d > start_date]
        if len(future_days) >= n_days:
            return future_days[n_days - 1]
        return future_days[-1] if future_days else start_date

    def check_filter(self, symbol: str, current_date, current_low: float) -> bool:
        if symbol not in self.buy_records:
            return False
        record = self.buy_records[symbol]
        if current_date > record["expire_date"]:
            if symbol in self.buy_records:
                del self.buy_records[symbol]
            return False
        if current_low < record["buy_day_low"]:
            if symbol in self.buy_records:
                del self.buy_records[symbol]
            return True
        return False

    def clear(self, symbol: str):
        if symbol in self.buy_records:
            del self.buy_records[symbol]
