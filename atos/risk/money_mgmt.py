"""资金管理"""
import pandas as pd


class MoneyManager:
    """资金管理器 - 5 级保护"""

    def __init__(self, initial_equity: float = 1_000_000):
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.daily_loss = 0.0
        self.daily_reset_date = None
        self.month_loss = 0.0
        self.month_start_date = None
        self.quarter_loss = 0.0
        self.quarter_start_date = None
        self.year_loss = 0.0
        self.year_start_date = None
        self.single_stock_loss_limit = -0.03

    def check_single_stock_loss(self, position, current_price: float = None) -> bool:
        if position.entry_price <= 0:
            return False
        if current_price is None:
            current_price = getattr(position, "last_price", position.entry_price)
        pnl_pct = (current_price / position.entry_price) - 1
        threshold = getattr(self, "single_stock_loss_limit", -0.03)
        return pnl_pct <= threshold

    def update_pnl(self, pnl: float, current_date: pd.Timestamp,
                    current_equity: float) -> dict:
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # 重置窗口
        if self.daily_reset_date != current_date:
            self.daily_loss = 0
            self.daily_reset_date = current_date

        if not self.month_start_date or current_date.month != self.month_start_date.month:
            self.month_loss = 0
            self.month_start_date = current_date

        if not self.quarter_start_date or (current_date.month - 1) // 3 != (self.quarter_start_date.month - 1) // 3:
            self.quarter_loss = 0
            self.quarter_start_date = current_date

        if not self.year_start_date or current_date.year != self.year_start_date.year:
            self.year_loss = 0
            self.year_start_date = current_date

        self.daily_loss += pnl
        self.month_loss += pnl
        self.quarter_loss += pnl
        self.year_loss += pnl

        peak = self.peak_equity if self.peak_equity > 0 else 1
        daily_loss_pct = self.daily_loss / peak
        month_loss_pct = self.month_loss / peak
        quarter_loss_pct = self.quarter_loss / peak
        year_loss_pct = self.year_loss / peak

        result = {
            "should_clear_stock": False,
            "should_stop_trading": False,
            "position_multiplier": 1.0,
            "should_force_empty": False,
        }

        if daily_loss_pct < -0.02:
            result["should_stop_trading"] = True

        if month_loss_pct < -0.05:
            result["position_multiplier"] = 0.5

        if quarter_loss_pct < -0.10:
            result["position_multiplier"] = 0.33

        if year_loss_pct < -0.15:
            result["should_force_empty"] = True

        return result
