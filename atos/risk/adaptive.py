"""spec §6.1 五大自适应参数

实现以下自适应调整：
- 持仓周期：滚动 20 日胜率 > 60% 延长 +2 天；< 45% 缩短 -2 天
- 开仓阈值：base + (0.5 - rolling_winrate_20d) × 0.3
- 仓位上限：乘以 market_breadth（沪深 300 站上 MA60 的比例）

因子权重调整（spec §7.3）在 selection/weight_schedule.py 中实现。
止损倍数 k 调整已在 stop_loss.py 中实现（vol_adj）。
"""
import logging
from collections import deque
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("atos")


class AdaptiveTracker:
    """自适应参数跟踪器

    维护：
    - 滚动 N 笔平仓交易（计算 rolling_winrate）
    - market_breadth（每日沪深 300 站上 MA60 的比例）
    """

    def __init__(self, config, market_df: Optional[pd.DataFrame] = None,
                 window: int = 20):
        self.config = config
        self.window = window
        self._recent_trades = deque(maxlen=window)
        self._breadth_cache = {}
        if market_df is not None:
            self._precompute_breadth(market_df)

    def _precompute_breadth(self, market_df: pd.DataFrame):
        """预计算每日 market_breadth

        简化：单一沪深 300 指数，用 close vs MA60 站上比例。
        指数站上 MA60 时 breadth=1.0，否则 0.0（占位简化，spec 要求是成份股比例）。
        """
        if "MA60" not in market_df.columns or "close" not in market_df.columns:
            return
        above = (market_df["close"] > market_df["MA60"]).fillna(False)
        for d, v in above.items():
            self._breadth_cache[d] = 1.0 if v else 0.0

    def record_trade(self, pnl_pct: float, exit_date: pd.Timestamp):
        """记录一笔平仓交易"""
        self._recent_trades.append({"pnl_pct": pnl_pct, "date": exit_date})

    @property
    def rolling_winrate(self) -> float:
        """滚动胜率（基于最近 N 笔平仓交易）"""
        if len(self._recent_trades) == 0:
            return 0.5
        wins = sum(1 for t in self._recent_trades if t["pnl_pct"] > 0)
        return wins / len(self._recent_trades)

    def get_market_breadth(self, date: pd.Timestamp) -> float:
        """获取当日 market_breadth"""
        if date in self._breadth_cache:
            return self._breadth_cache[date]
        valid = [d for d in self._breadth_cache.keys() if d <= date]
        if valid:
            return self._breadth_cache[max(valid)]
        return 1.0

    def get_adaptive_holding_period(self, regime: str) -> int:
        """spec §6.1 持仓周期自适应

        - 胜率 > 60% → 延长 +2 天
        - 胜率 < 45% → 缩短 -2 天
        """
        base = self.config.max_holding_days.get(regime, 20)
        winrate = self.rolling_winrate
        if winrate > 0.60:
            return base + 2
        elif winrate < 0.45:
            return max(base - 2, 1)
        return base

    def get_adaptive_open_threshold(self, regime: str) -> float:
        """spec §6.1 开仓阈值自适应

        threshold = base + (0.5 - rolling_winrate_20d) × 0.3
        """
        base = self.config.open_threshold_by_regime.get(regime, 0.70)
        winrate = self.rolling_winrate
        return base + (0.5 - winrate) * 0.3

    def get_adaptive_position_cap(self, regime: str, date: pd.Timestamp) -> float:
        """spec §6.1 仓位上限自适应

        cap = base × market_breadth，breadth 范围 [0.5, 1.0]
        """
        if regime == "CRASH":
            return 0.0
        base = self.config.base_position.get(regime, 0.5)
        breadth = self.get_market_breadth(date)
        # 简单映射：breadth in {0.0, 1.0} → multiplier in {0.5, 1.0}
        breadth_mult = 0.5 + 0.5 * breadth
        return base * breadth_mult

    def get_adaptive_kelly_multiplier(self) -> float:
        """ATOS2 v2: 自适应 Kelly 乘数

        胜率≥60% → kelly_mult = base × adaptive_high (上限 1.0)
        胜率 40-60% → kelly_mult = base
        胜率<40% → kelly_mult = base × adaptive_low (下限 0.1)
        """
        base = getattr(self.config, "kelly_multiplier", 0.0)
        if not getattr(self.config, "adaptive_kelly_enabled", False):
            return base
        if base <= 0:
            return 0.0
        high_mult = getattr(self.config, "kelly_adaptive_high", 1.5)
        low_mult = getattr(self.config, "kelly_adaptive_low", 0.5)
        winrate = self.rolling_winrate
        if winrate >= 0.60:
            return min(base * high_mult, 1.0)
        elif winrate < 0.40:
            return max(base * low_mult, 0.1)
        return base
