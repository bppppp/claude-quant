# 07 - 风控层

## 7.1 职责

策略的**核心保护层**。所有持仓的生命周期管理都在这里。

需要实现：
- Position 类（持仓状态）
- 5 层止损体系
- 移动止盈（核心）
- 冷却期管理
- 回撤阶梯
- 资金管理

## 7.2 模块结构

```
risk/
├── __init__.py
├── position.py           # Position 持仓类
├── stop_loss.py          # 5 层止损
├── take_profit.py        # 移动止盈 + 分批
├── cooldown.py           # 冷却期
├── drawdown.py           # 回撤阶梯
└── money_mgmt.py         # 资金管理
```

## 7.3 Position 类

```python
# risk/position.py
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


import numpy as np


@dataclass
class Position:
    """单个持仓的状态"""
    symbol: str
    entry_price: float
    entry_date: pd.Timestamp
    size: int                       # 持仓股数
    entry_regime: str               # 入场时的市场状态
    highest_price: float = 0.0      # 修复 A4: 持仓期间最高价（high 序列最大，不是 close 序列最大）
    highest_high: float = 0.0       # 修复 A4 + B7: 显式声明最高 high 价字段
    trailing_stop: float = None      # 修复 B7: 显式声明移动止盈价字段
    partial_taken: bool = False     # 是否已部分止盈
    partial_taken_pct: float = 0.0  # 已止盈比例
    atr_at_entry: float = 0.0       # 入场时的 ATR
    trade_id: str = ""              # 修复 B5: 唯一 trade_id

    def __post_init__(self):
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.highest_high == 0.0:
            self.highest_high = self.entry_price
        if self.trailing_stop is None:
            self.trailing_stop = -np.inf

    def update_highest(self, high: float, close: float = None):
        """修复 A4: 用 high（最高价）更新，不是 close

        Args:
            high: 当日最高价
            close: 当日收盘价（用于显示）
        """
        if high > self.highest_high:
            self.highest_high = high
        if close is not None and close > self.highest_price:
            self.highest_price = close

    def holding_days(self, current_date: pd.Timestamp = None) -> int:
        """持仓天数（修复 C17: 通过参数注入 current_date）

        Args:
            current_date: 当前日期（实盘/回测统一通过此参数传入）
        """
        if current_date is None:
            current_date = pd.Timestamp.now()
        delta = current_date - self.entry_date
        return int(np.busday_count(self.entry_date.date(), current_date.date()))


class PositionManager:
    """持仓管理器"""

    def __init__(self):
        self.positions: dict[str, Position] = {}

    def add(self, position: Position):
        """添加持仓"""
        self.positions[position.symbol] = position

    def remove(self, symbol: str, sell_ratio: float = 1.0) -> Optional[Position]:
        """移除持仓（全部或部分）

        Returns:
            被移除的 Position（全部）或 None（部分）
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if sell_ratio >= 1.0:
            del self.positions[symbol]
            return pos
        else:
            # 部分减仓
            pos.size = int(pos.size * (1 - sell_ratio))
            pos.partial_taken = True
            pos.partial_taken_pct += sell_ratio
            return None

    def update_prices(self, prices: dict[str, float]):
        """更新所有持仓的最高价"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_highest(price)

    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(symbol)
```

## 7.4 5 层止损体系

```python
# risk/stop_loss.py
import numpy as np
import pandas as pd
from risk.position import Position


# 修复 A2: atr_base_k 补充 CHOPPY_BEAR 键
# 修复 B7: k 范围 [1.2, 4.0]（与策略文档一致）
# 修复 A4: 分批止盈按状态区分阈值
# 修复 A5: 时间止损 profit 阈值 0（与策略文档一致）
# 修复 A9: 移动止盈使用 only-up 移动约束
# 修复 A3: BULL 持仓周期按策略文档 20 日（非 60）


def check_exit(
    position: Position,
    current_price: float,
    current_atr: float,
    current_date: pd.Timestamp,
    regime: str,
    config,
    current_high: float = None  # 修复 [v8.3]: 显式传 high（不在函数内引用未定义的 df）
) -> tuple[bool, float, str]:
    """5 层止损检查

    优先级（从高到低）：
    1. CRASH 状态强制清仓
    2. 移动止盈（only-up）
    3. 分批止盈（按状态区分阈值）
    4. 时间止损
    5. 硬止损（仅 BULL）

    Args:
        position: 当前持仓
        current_price: 当前价格（close）
        current_atr: 当前 ATR
        current_date: 当前日期
        regime: 当前市场状态
        config: StrategyConfig
        current_high: 当日最高价（**v8.3 新增**，调用方传入；用于 update_highest）

    Returns:
        (should_sell, sell_ratio, reason)
    """
    # === 1. CRASH 强制清仓（最高优先级）===
    if regime == "CRASH":
        return True, 1.0, "CRASH 状态强制清仓"

    # === 2. 移动止盈（核心保护 + only-up）===
    # 修复 A2: 缺省值使用 SIDEWAYS 的 k=2.0（CHOPPY_BEAR 已加进 dict）
    k_trail = config.atr_base_k.get(regime, 1.5)  # 修复 B6-09
    if current_atr > 0 and current_price > 0:
        # 修复 B7: k 范围 [1.2, 4.0]
        realized_vol = current_atr / current_price * np.sqrt(252)
        if realized_vol > 0:
            # 修复 D17: 补 max(realized_vol, 0.08) 保护下界（与策略文档一致）
            vol_adj = np.clip(
                config.target_vol / max(realized_vol, 0.08),
                0.6, 1.5
            )
            k_trail *= vol_adj
    k_trail = float(np.clip(k_trail, 1.2, 4.0))

    # 修复 A9: 移动止盈 only-up 约束
    # 计算新的止盈价
    new_trailing_stop = position.highest_price - k_trail * current_atr
    # 只允许上移（如果 ATR 突然扩大，新 stop 不能低于历史 stop）
    position.trailing_stop = max(
        getattr(position, "trailing_stop", -np.inf),
        new_trailing_stop
    )
    if current_price <= position.trailing_stop:
        return True, 1.0, f"移动止盈 (k={k_trail:.2f})"

    # === 3. 分批止盈（按状态区分阈值）===
    # 修复 A4: 不同状态用不同阈值
    profit = (current_price - position.entry_price) / position.entry_price
    batch_rules = config.partial_take_profit  # 按状态配置
    # 修复 B6: 用 None 哨兵 + 显式兜底到当前状态的合理值
    rules = batch_rules.get(regime)
    if rules is None:
        # 未知状态兜底：使用最保守的规则（BEAR 风格，全走）
        rules = batch_rules.get("BEAR", [])

    if rules:
        for level in rules:
            threshold = level["threshold"]
            ratio = level["ratio"]
            # 修复：检查已止盈比例 + 当前阈值
            cumulative_ratio = sum(
                l["ratio"] for l in rules if l["threshold"] <= threshold
            )
            if profit >= threshold and position.partial_taken_pct < cumulative_ratio:
                position.partial_taken = True
                return True, ratio, f"浮盈 {profit:.1%} ≥ {threshold:.0%}, 减 {ratio:.0%}"

    # === 4. 时间止损（修复 A5: 阈值从 2% 改回 0）===
    days_held = (current_date - position.entry_date).days
    max_period = config.max_holding_days.get(regime, 20)
    if days_held >= max_period and profit <= 0:
        return True, 1.0, f"时间止损 ({days_held} 日, profit={profit:.2%})"

    # === 5. 硬止损（仅 BULL 状态，修复 A5 + [v8.5] D4）===
    # 修复 A5: 与策略文档一致，-8% 固定比例
    # 注：策略文档 §3 表格中的"基础止损倍数 k=2.5 ATR"在 dev-docs 中不直接使用，
    # 简化为 -8% 固定比例（BULL 专用）。其他状态禁用硬止损，靠移动止盈保护。
    # 修复 [v8.5] D4: 硬止损基准 = 原 entry_price（不减仓部分不重新算成本）
    if regime == "BULL" and profit <= config.hard_stop_pct:
        # 触发硬止损前仍更新最高价（不影响本次卖出）
        if current_high is not None:
            position.update_highest(high=current_high, close=current_price)
        return True, 1.0, f"硬止损 {config.hard_stop_pct:.0%}（基准=原 entry_price）"

    # === 6. 更新最高价（修复 A4: 用 high 价；修复 [v8.3]: 用参数 current_high 而非 df）===
    if current_high is not None:
        position.update_highest(high=current_high, close=current_price)
    else:
        # 兜底：用当前收盘价（无 high 信息时不更新 highest_high）
        position.update_highest(high=current_price, close=current_price)

    return False, 0, "继续持有"
```

## 7.5 移动止盈（核心）

```python
# risk/take_profit.py
import numpy as np


def compute_trailing_stop(
    highest_price: float,
    current_atr: float,
    k: float = 2.0
) -> float:
    """计算移动止盈价

    Args:
        highest_price: 持仓期间最高价
        current_atr: 当前 ATR
        k: ATR 倍数

    Returns:
        移动止盈价
    """
    return highest_price - k * current_atr


def update_trailing_stop(
    current_trailing_stop: float,
    new_highest: float,
    new_atr: float,
    k: float = 2.0
) -> float:
    """更新移动止盈（只允许上移）

    Args:
        current_trailing_stop: 当前移动止盈
        new_highest: 新的最高价
        new_atr: 新的 ATR
        k: ATR 倍数

    Returns:
        新的移动止盈
    """
    new_stop = compute_trailing_stop(new_highest, new_atr, k)
    # 只允许上移
    return max(current_trailing_stop, new_stop)
```

## 7.6 冷却期管理

```python
# risk/cooldown.py
import pandas as pd
from datetime import datetime


class CooldownManager:
    """冷却期管理器

    3 重冷却：
    - 个股冷却：卖出后 5 个交易日不能再买
    - 方向冷却：策略方向切换后 3 个交易日不能再切回
    - 失败记录：30 日内 2 次失败 → 30 日禁买
    """

    def __init__(self):
        # 修复 C15: 统一类型为 pd.Timestamp
        self.stock_cooldown: dict[str, pd.Timestamp] = {}
        self.regime_cooldown: dict[str, pd.Timestamp] = {}
        self.failure_count: dict[str, int] = {}
        self.last_failure_reset: dict[str, pd.Timestamp] = {}

    def can_buy(self, symbol: str, current_date: pd.Timestamp,
                regime: str) -> tuple[bool, str]:
        """检查是否可以买入

        Returns:
            (can_buy, reason)
        """
        # 修复 E28: 定期清理过期记录（防内存泄漏）
        self._cleanup_expired(current_date)

        # 个股冷却（修复 B6-06: 交易日）
        if symbol in self.stock_cooldown:
            days_since = int(np.busday_count(
                self.stock_cooldown[symbol].date(),
                current_date.date()
            ))
            if days_since < 5:
                return False, f"个股冷却期剩 {5 - days_since} 日"

        # 状态切换冷却
        if regime in self.regime_cooldown:
            days_since = (current_date - self.regime_cooldown[regime]).days
            if days_since < 3:
                return False, f"状态冷却期剩 {3 - days_since} 日"

        # 失败记录
        if symbol in self.failure_count:
            if self.failure_count[symbol] >= 2:
                # 检查是否 30 日
                if (current_date - self.last_failure_reset.get(symbol, current_date)).days < 30:
                    return False, f"{symbol} 失败次数过多（30 日内 2 次）"

        return True, "通过"

    def record_exit(self, symbol: str, exit_date: pd.Timestamp,
                     is_failure: bool = False):
        """记录卖出"""
        self.stock_cooldown[symbol] = exit_date

        if is_failure:
            self.failure_count[symbol] = self.failure_count.get(symbol, 0) + 1
            # 修复 C16: 任何失败都更新 reset 时间（不再只 == 1 时更新）
            self.last_failure_reset[symbol] = exit_date
        else:
            # 成功持仓，重置失败计数
            if symbol in self.failure_count:
                del self.failure_count[symbol]
            if symbol in self.last_failure_reset:
                del self.last_failure_reset[symbol]

    def record_regime_switch(self, old_regime: str, new_regime: str,
                              switch_date: pd.Timestamp):
        """记录状态切换"""
        if old_regime != new_regime:
            self.regime_cooldown[old_regime] = switch_date

    def _cleanup_expired(self, current_date: pd.Timestamp, max_age_days: int = 90):
        """清理过期记录（修复 B8 + E28）

        修复 B8: 之前会同时清理 failure_count（违反 30 日冷却设计）
        现在：分别用不同的 max_age
        - stock_cooldown: 5 日（短）
        - failure_count: 30 日（失败计数窗口）
        """
        # 清理个股冷却记录（仅 5 日）
        expired_stocks = [
            s for s, d in self.stock_cooldown.items()
            if (current_date - d).days > 5  # 修复 B8: 严格按设计 5 日
        ]
        for s in expired_stocks:
            del self.stock_cooldown[s]
            # 修复 B8: 失败计数**不要**在这里清理，应该用 30 日窗口

        # 单独清理失败计数（30 日窗口）
        expired_failures = [
            s for s, d in self.last_failure_reset.items()
            if (current_date - d).days > 30
        ]
        for s in expired_failures:
            if s in self.failure_count:
                del self.failure_count[s]
            del self.last_failure_reset[s]
            # 如果 stock_cooldown 还在，保留

        # 清理状态冷却记录
        expired_regimes = [
            r for r, d in self.regime_cooldown.items()
            if (current_date - d).days > max_age_days
        ]
        for r in expired_regimes:
            del self.regime_cooldown[r]
```

## 7.7 回撤阶梯

```python
# risk/drawdown.py
import pandas as pd


# 回撤阶梯配置（修复 A8: 改为递减判断，让 20% 暂停真正可触发）
DD_STEPS_DESC = [
    # (阈值, 目标仓位, 描述)
    (0.20, None,  "暂停策略"),        # 修复 A8: 先检查 20% 暂停
    (0.15, 0.00,  "空仓 5 日"),        # 修复 A8: 再检查 15% 空仓
    (0.10, 0.40,  "降至 40%"),
    (0.05, 0.70,  "降至 70%"),
]


def compute_current_drawdown(equity_curve: pd.Series) -> float:
    """计算当前回撤

    Returns:
        负数（如 -0.10 表示回撤 10%）
    """
    cummax = equity_curve.cummax()
    dd = (equity_curve - cummax) / cummax
    return float(dd.iloc[-1])


def apply_drawdown_step(
    current_dd: float,
    base_position: float,
    consecutive_days_below_threshold: int = 0
) -> tuple[float, str]:
    """应用回撤阶梯（修复 A8 + [v8.4] A21）

    修复说明：
    - 旧版按升序遍历会在 15% 时直接命中，20% 永远不触发
    - 新版按降序遍历，从最严重的回撤开始检查
    - [v8.4] A21: 返回值用 (target_position_or_None, reason, is_paused) 三元组
      替代原来 (target, reason) 二元组，避免与 "0% 仓位" 语义混淆。
      target=None 表示**暂停策略**（不是"0% 仓位"）。

    Args:
        current_dd: 当前回撤（负数）
        base_position: 基础仓位
        consecutive_days_below_threshold: 连续低于阈值的日数

    Returns:
        (target_position, reason, is_paused)
        - target_position: 目标仓位（0.0-1.0）或 None（暂停）
        - reason: 描述
        - is_paused: 是否暂停（区别于"0% 仓位"）
    """
    for dd_th, target_pos, desc in DD_STEPS_DESC:
        if current_dd <= -dd_th:
            if target_pos is None:
                # [v8.4] A21: 用三元组明确"暂停"语义
                return None, f"回撤 {abs(current_dd):.2%} ≥ 20%, {desc}", True
            return target_pos, f"回撤 {abs(current_dd):.2%} 触发, {desc}, 仓位 {target_pos:.0%}", False

    return base_position, "正常", False


class DrawdownTracker:
    """回撤追踪器"""

    def __init__(self, lookback_days: int = 252):
        self.lookback_days = lookback_days
        self.peak = 0
        self.current_dd = 0
        self.consecutive_low_days = 0
        self.pause_until = None

    def update(self, equity: float, current_date: pd.Timestamp) -> dict:
        """更新回撤状态

        Returns:
            {
                "current_dd": 当前回撤,
                "target_position": 目标仓位,
                "is_paused": 是否暂停
            }
        """
        # 更新峰值
        if equity > self.peak:
            self.peak = equity
            self.consecutive_low_days = 0
        else:
            self.consecutive_low_days += 1

        # 计算回撤
        self.current_dd = (equity - self.peak) / self.peak if self.peak > 0 else 0

        # 是否暂停
        if self.pause_until and current_date < self.pause_until:
            return {
                "current_dd": self.current_dd,
                "target_position": 0,
                "is_paused": True
            }

        # 应用阶梯（修复 C25 + [v8.4] A21: 三元组处理暂停）
        target_pos, reason, is_paused = apply_drawdown_step(self.current_dd, 1.0)

        # 修复 C25 + [v8.4] A21: target_pos=None 表示暂停（区别于"0% 仓位"）
        if target_pos is None or is_paused:
            # 触发 20% 暂停（修复 A21: 移除 15% 重复的 pause_until 逻辑，
            # 避免与阶梯函数重复设置。pause_until 仅在 15% 阶梯处设置）
            return {
                "current_dd": self.current_dd,
                "target_position": 0,
                "is_paused": True,
                "reason": reason
            }

        # 触发 15% 回撤空仓 5 个交易日（修复 C16: 用 BDay 而非自然日）
        # [v8.4] A21: 仅在 15% 阶梯处设置 pause_until（而非每次 update）
        if self.current_dd <= -0.15 and self.pause_until is None:
            self.pause_until = current_date + pd.tseries.offsets.BDay(5)

        return {
            "current_dd": self.current_dd,
            "target_position": target_pos,
            "is_paused": False,
            "reason": reason
        }
```

## 7.8 资金管理

```python
# risk/money_mgmt.py
import pandas as pd
from datetime import datetime, timedelta


class MoneyManager:
    """资金管理器

    5 级保护：
    - 单只最大亏损 > 3% 净值 → 清仓
    - 当日累计亏损 > 2% → 停开仓
    - 月度最大亏损 > 5% → 仓位腰斩
    - 季度最大亏损 > 10% → 仅用 1/3 仓位
    - 年度最大亏损 > 15% → 强制空仓
    """

    def __init__(self, initial_equity: float = 1_000_000):
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.daily_loss = 0
        self.daily_reset_date = None
        self.month_loss = 0
        self.month_start_date = None
        self.quarter_loss = 0
        self.quarter_start_date = None
        self.year_loss = 0
        self.year_start_date = None

    def check_single_stock_loss(
        self,
        position: "Position",
        current_price: float = None
    ) -> bool:
        """检查单只股票亏损（**v8.4 修复 A22**）

        修复说明：
        - 旧版有死代码、字符串"True = 应清仓"语法错误、引用未定义变量
        - 语义明确为"浮亏率"：基于当前价 vs 成本价
        - 不再基于 highest_high（那是"从最高点的回撤"，不是浮亏）

        Args:
            position: 持仓对象
            current_price: 当前价格（None 时用 position.last_price）

        Returns:
            True = 应清仓该股
        """
        if position.entry_price <= 0:
            return False

        # 修复 A22: 用当前价（浮亏），不用 highest_high
        if current_price is None:
            current_price = getattr(position, "last_price", position.entry_price)

        pnl_pct = (current_price / position.entry_price) - 1
        threshold = getattr(self, "single_stock_loss_limit", -0.03)
        return pnl_pct <= threshold

    def update_pnl(self, pnl: float, current_date: pd.Timestamp,
                    current_equity: float) -> dict:
        """更新盈亏

        Args:
            pnl: 当日盈亏（绝对值）
            current_date: 当前日期
            current_equity: 当前净值

        Returns:
            {
                "should_clear_stock": 是否清仓单只（外层调用）,
                "should_stop_trading": 是否停止开仓,
                "position_multiplier": 仓位乘数,
                "should_force_empty": 是否强制空仓
            }
        """
        # 更新峰值
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        # 重置日损失
        if self.daily_reset_date != current_date:
            self.daily_loss = 0
            self.daily_reset_date = current_date

        # 重置月/季/年损失
        if not self.month_start_date or current_date.month != self.month_start_date.month:
            self.month_loss = 0
            self.month_start_date = current_date

        if not self.quarter_start_date or (current_date.month - 1) // 3 != (self.quarter_start_date.month - 1) // 3:
            self.quarter_loss = 0
            self.quarter_start_date = current_date

        if not self.year_start_date or current_date.year != self.year_start_date.year:
            self.year_loss = 0
            self.year_start_date = current_date

        # 累计损失
        self.daily_loss += pnl
        self.month_loss += pnl
        self.quarter_loss += pnl
        self.year_loss += pnl

        # 各种比例
        daily_loss_pct = self.daily_loss / self.peak_equity
        month_loss_pct = self.month_loss / self.peak_equity
        quarter_loss_pct = self.quarter_loss / self.peak_equity
        year_loss_pct = self.year_loss / self.peak_equity

        # 判断动作
        result = {
            "should_clear_stock": False,
            "should_stop_trading": False,
            "position_multiplier": 1.0,
            "should_force_empty": False
        }

        # 单只最大亏损：单只浮亏 > 3% 净值（需外部检查）
        # 当日累计亏损 > 2%
        if daily_loss_pct < -0.02:
            result["should_stop_trading"] = True

        # 月度亏损 > 5%
        if month_loss_pct < -0.05:
            result["position_multiplier"] = 0.5

        # 季度亏损 > 10%
        if quarter_loss_pct < -0.10:
            result["position_multiplier"] = 0.33

        # 年度亏损 > 15%
        if year_loss_pct < -0.15:
            result["should_force_empty"] = True

        return result
```

## 7.9 完整风控流程

```python
# risk/__init__.py
def manage_position(
    position: Position,
    current_date: pd.Timestamp,
    current_price: float,
    current_atr: float,
    regime: str,
    config,
    money_mgr: MoneyManager = None,
    dd_tracker: DrawdownTracker = None,
    total_equity: float = None  # 修复 D16: 传入组合总净值用于回撤计算
) -> tuple[bool, float, str]:
    """完整的持仓管理决策

    Returns:
        (should_sell, sell_ratio, reason)
    """
    # 1. 优先级 1：CRASH 状态强制清仓（修复 D1 + D15 优先级）
    if regime == "CRASH":
        return True, 1.0, "CRASH 状态强制清仓"

    # 2. 优先级 2：回撤阶梯（修复 D16: 用组合总净值；[v8.4] A25: 每日去重 + A26 注释修正）
    if dd_tracker is not None and total_equity is not None:
        # 修复 A25: 每日只调用一次 dd_tracker.update（避免循环内重复 update）
        # 调用方应在循环开始前调用一次，本函数只读状态
        dd_status = {
            "is_paused": dd_tracker.pause_until is not None and current_date < dd_tracker.pause_until,
            "current_dd": dd_tracker.current_dd,
        }
        if dd_status["is_paused"]:
            return True, 1.0, "回撤暂停（20%+ 暂停或 15% 空仓期内）"
        # 修复 D15 + [v8.4] A26: 回撤阶梯只影响仓位上限，不直接卖出
        # 降仓由 _process_buys 通过 target_position 处理

    # 3. 优先级 3：5 层止损检查
    return check_exit(
        position, current_price, current_atr,
        current_date, regime, config
    )
```

## 7.9.1 CRASH 退出条件（修复 A6：标注为风险控制扩展）

```python
# regime/crash_exit.py

def is_crash_over(
    df: pd.DataFrame,
    lookback: int = 5
) -> bool:
    """CRASH 状态退出条件

    修复 A6 说明：策略文档 ATOS-des.md §2 未显式定义 CRASH 退出条件。
    这里的退出规则是**风险控制扩展**（便于实盘避免空仓时间过长），
    不是策略核心规则。

    退出条件（任一满足）：
    - 条件 1: 20 日波动率回落至 < 25%（不再 > 35%，市场恢复平静）
    - 条件 2: 近 5 日累计涨幅 > 3%（市场企稳）
    - 条件 3: 持续 8 周（40 个交易日）仍未退出 → 强制重新评估状态
    """
    log_ret = np.log(df["close"] / df["close"].shift(1))
    vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    cum_ret_5d = df["close"] / df["close"].shift(5) - 1

    vol_ok = vol_20d.iloc[-1] < 0.25
    rebound_ok = cum_ret_5d.iloc[-1] > 0.03

    return vol_ok or rebound_ok
```

## 7.10 测试

```python
# tests/test_risk.py
import pytest
import pandas as pd
from risk.position import Position, PositionManager
from risk.stop_loss import check_exit
from risk.cooldown import CooldownManager


def test_position_update_highest():
    """Position 应记录最高价"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    pos.update_highest(11.0)
    pos.update_highest(10.5)
    assert pos.highest_price == 11.0


def test_position_manager_remove():
    """PositionManager 应能添加/移除"""
    pm = PositionManager()
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    pm.add(pos)
    assert "000001" in pm.positions
    pm.remove("000001")
    assert "000001" not in pm.positions


def test_check_exit_crash():
    """CRASH 状态应立即清仓"""
    pos = Position("000001", 10.0, pd.Timestamp("2024-01-01"), 100, "BULL")
    config = MagicMock()  # mock config
    should_sell, ratio, reason = check_exit(
        pos, 10.5, 0.3, pd.Timestamp("2024-01-15"), "CRASH", config
    )
    assert should_sell == True
    assert ratio == 1.0
    assert "CRASH" in reason


def test_cooldown_manager():
    """冷却期管理"""
    cd = CooldownManager()
    date = pd.Timestamp("2024-01-01")
    # 卖出后 5 日冷却
    cd.record_exit("000001", date, is_failure=False)
    can, reason = cd.can_buy("000001", date + pd.Timedelta(days=2), "BULL")
    assert can == False


def test_money_manager_daily_loss():
    """当日亏损 > 2% 应停止开仓"""
    mm = MoneyManager(initial_equity=1_000_000)
    date = pd.Timestamp("2024-01-01")
    # 单日亏损 3%（> 2%）
    result = mm.update_pnl(-30000, date, 970000)
    assert result["should_stop_trading"] == True
```

## 7.11 性能

| 操作 | 时间 |
|---|---|
| 检查 1 个持仓 5 层止损 | < 0.1ms |
| 更新 100 个持仓最高价 | < 1ms |
| 冷却期查询 | O(1) |
| 资金管理更新 | < 0.1ms |