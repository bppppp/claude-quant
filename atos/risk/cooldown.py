"""冷却期管理"""
import numpy as np
import pandas as pd


class CooldownManager:
    """冷却期管理器"""

    def __init__(self):
        self.stock_cooldown: dict = {}
        self.regime_cooldown: dict = {}
        self.failure_count: dict = {}
        self.last_failure_reset: dict = {}

    def can_buy(self, symbol: str, current_date: pd.Timestamp, regime: str) -> tuple:
        self._cleanup_expired(current_date)

        # 个股冷却（5 个交易日）
        if symbol in self.stock_cooldown:
            days_since = int(np.busday_count(
                self.stock_cooldown[symbol].date(),
                current_date.date()
            ))
            if days_since < 5:
                return False, f"个股冷却期剩 {5 - days_since} 日"

        # 状态切换冷却（3 日）
        if regime in self.regime_cooldown:
            days_since = (current_date - self.regime_cooldown[regime]).days
            if days_since < 3:
                return False, f"状态冷却期剩 {3 - days_since} 日"

        # 失败计数（30 日内 2 次失败）
        if symbol in self.failure_count and self.failure_count[symbol] >= 2:
            if (current_date - self.last_failure_reset.get(symbol, current_date)).days < 30:
                return False, f"{symbol} 失败次数过多（30 日内 2 次）"

        return True, "通过"

    def record_exit(self, symbol: str, exit_date: pd.Timestamp, is_failure: bool = False):
        self.stock_cooldown[symbol] = exit_date
        if is_failure:
            self.failure_count[symbol] = self.failure_count.get(symbol, 0) + 1
            self.last_failure_reset[symbol] = exit_date
        else:
            if symbol in self.failure_count:
                del self.failure_count[symbol]
            if symbol in self.last_failure_reset:
                del self.last_failure_reset[symbol]

    def record_regime_switch(self, old_regime: str, new_regime: str, switch_date: pd.Timestamp):
        if old_regime != new_regime:
            self.regime_cooldown[old_regime] = switch_date

    def _cleanup_expired(self, current_date: pd.Timestamp, max_age_days: int = 90):
        # 个股冷却（5 日）
        expired_stocks = [
            s for s, d in self.stock_cooldown.items()
            if (current_date - d).days > 5
        ]
        for s in expired_stocks:
            del self.stock_cooldown[s]

        # 失败计数（30 日）
        expired_failures = [
            s for s, d in self.last_failure_reset.items()
            if (current_date - d).days > 30
        ]
        for s in expired_failures:
            if s in self.failure_count:
                del self.failure_count[s]
            del self.last_failure_reset[s]

        # 状态冷却（max_age_days）
        expired_regimes = [
            r for r, d in self.regime_cooldown.items()
            if (current_date - d).days > max_age_days
        ]
        for r in expired_regimes:
            del self.regime_cooldown[r]
