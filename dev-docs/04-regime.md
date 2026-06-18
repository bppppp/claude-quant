# 04 - 状态识别层

## 4.1 职责

**先判大势，再论个股**。本层是整个策略的核心，所有交易决策都必须先经过市场状态判断。

需要实现：
- 4 状态分类器（BULL / SIDEWAYS / BEAR / CRASH）
- 状态确认机制（迟滞 + 冷却期）
- 震荡下行检测（叠加在 BEAR/SIDEWAYS 上）

## 4.2 模块结构

```
regime/
├── __init__.py
├── market_regime.py        # 4 状态分类
├── hysteresis.py            # 状态迟滞机制
├── choppy_bear.py           # 震荡下行检测
└── combined.py              # 综合状态（市场状态 + 震荡下行叠加）
```

## 4.3 4 状态定义

| 状态 | 特征 | 默认仓位 |
|---|---|---|
| BULL | 趋势上行 | 80-100% |
| SIDEWAYS | 无明显方向 | 50-70% |
| BEAR | 趋势下行 | 10-20% |
| CRASH | 急跌 | 0-10% |

> **v8.1 更新**：4 状态识别**基于大盘指数数据**（沪深 300 等）。
> 数据源：`data/data-benchmark/`（10 指数 × 10 年，详见 02-data-layer.md §2.4.3）。
> **关键**：策略运行**前**必须先加载大盘指数 K 线，作为 `df` 参数传入 `detect_market_regime()`。

## 4.4 4 状态分类器实现（**历史版本**，保留供参考）

> **修复 #4**：此版本为评分制实现，已被 §4.4.1 布尔规则版替代。**新代码请直接用 §4.4.1**。

```python
# regime/market_regime_score_based.py  (legacy, 修复 #4)
import pandas as pd
import numpy as np
from typing import Tuple

def detect_market_regime(
    df: pd.DataFrame,
    bull_th: float = 70,
    bear_th: float = 30,
    crash_th: float = 15,
    crash_volatility_th: float = 0.35,
    crash_5d_drawdown: float = -0.08,
    crash_20d_drawdown: float = -0.15,
) -> pd.DataFrame:
    """4 状态市场分类器

    判定规则基于 5 维评分 + DMI 方向 + 急速 CRASH 条件。

    Args:
        df: 必须包含 MA20, MA60, MA120, MACD, ADX, PDI, NDI 列
        bull_th: 牛市评分阈值（默认 70）
        bear_th: 熊市评分阈值（默认 30）
        crash_th: 崩盘评分阈值（默认 15）
        crash_volatility_th: CRASH 波动率阈值（默认 35%）
        crash_5d_drawdown: CRASH 5 日跌幅阈值（默认 -8%）
        crash_20d_drawdown: CRASH 20 日跌幅阈值（默认 -15%）

    Returns:
        DataFrame with columns: [trend_score, state]
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    ma120 = df["MA120"]
    macd_bar = df["MACD"]
    adx = df["ADX"]
    pdi = df["PDI"]
    ndi = df["NDI"]

    # === 趋势强度评分（0-100）===
    ma_bull = ((ma20 > ma60) & (ma60 > ma120)).astype(int)
    macd_above = (macd_bar > 0).astype(int)
    adx_strong = (adx > 25).astype(int)
    price_above_ma60 = (close > ma60).astype(int)
    price_above_ma120 = (close > ma120).astype(int)

    trend_score = (
        ma_bull * 30 +
        macd_above * 20 +
        price_above_ma60 * 15 +
        price_above_ma120 * 15 +
        adx_strong * 20
    )

    # === 急速 CRASH 判定 ===
    log_ret = np.log(close / close.shift(1))
    realized_vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    drawdown_5d = close / close.shift(5) - 1
    drawdown_20d = close / close.shift(20) - 1

    crash_cond = (
        (drawdown_5d <= crash_5d_drawdown) |
        (drawdown_20d <= crash_20d_drawdown)
    )
    crash_volatility_cond = (
        (realized_vol_20d > crash_volatility_th) &
        (drawdown_5d < -0.05)
    )
    is_crash = crash_cond & crash_volatility_cond

    # === 状态判定 ===
    state = pd.Series("SIDEWAYS", index=df.index, dtype=object)

    # BULL：高分 + DMI 上升（修复 A6: 显式排除 CRASH）
    bull_mask = (trend_score >= bull_th) & (pdi > ndi) & (~is_crash)
    state[bull_mask] = "BULL"

    # BEAR：低分 + DMI 下降
    bear_mask = (trend_score <= bear_th) & (ndi > pdi) & (~is_crash)
    state[bear_mask] = "BEAR"

    # CRASH：急速下跌
    state[is_crash] = "CRASH"

    # SIDEWAYS：默认

    return pd.DataFrame({
        "trend_score": trend_score,
        "state": state,
        "realized_vol_20d": realized_vol_20d,
        "drawdown_5d": drawdown_5d,
        "drawdown_20d": drawdown_20d
    })
```
```

> **注意**：以上为历史"评分制"实现，已被 **4.4.1 布尔规则版** 替代（修复 A3）。

## 4.4.1 4 状态分类器（布尔规则版，**修复 A2+A3**）

```python
# regime/market_regime_v2.py
import pandas as pd
import numpy as np


def detect_market_regime(
    df: pd.DataFrame,
    crash_5d_drawdown: float = -0.08,
    crash_20d_drawdown: float = -0.15,
    crash_volatility_th: float = 0.35,
) -> pd.DataFrame:
    """4 状态市场分类器（**布尔规则版**）

    严格按 ATOS-des.md §2.1 布尔规则判定：

    **BULL**（同时满足 4 条件）：
    ① 收盘价 > MA60
    ② MA20 > MA60
    ③ 近 20 日涨幅 ≥ 5%
    ④ 20 日年化波动率 ≤ 30%

    **BEAR**（同时满足 3 条件）：
    ① 收盘价 < MA60
    ② MA20 < MA60
    ③ 近 20 日涨幅 ≤ -5%
    ④ 不属于 CRASH

    **CRASH**（**OR 关系**，修复 A2）：
    ① 近 5 日跌幅 ≥ 8% **或** 近 20 日跌幅 ≥ 15%
    ② （可选加速）20 日波动率 > 35% 且 5 日跌幅 > 5%

    **SIDEWAYS**：以上都不满足
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]

    log_ret = np.log(close / close.shift(1))
    realized_vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    pct_change_20d = close / close.shift(20) - 1
    drawdown_5d = close / close.shift(5) - 1
    drawdown_20d = close / close.shift(20) - 1

    # === 1. CRASH 判定（最高优先级，OR 关系，修复 A2）===
    crash_basic = (drawdown_5d <= crash_5d_drawdown) | (drawdown_20d <= crash_20d_drawdown)
    crash_acceleration = (realized_vol_20d > crash_volatility_th) & (drawdown_5d < -0.05)
    is_crash = crash_basic | crash_acceleration

    # === 2. BULL 判定（4 条件 AND，修复 A3）===
    is_bull = (
        (close > ma60) &
        (ma20 > ma60) &
        (pct_change_20d >= 0.05) &
        (realized_vol_20d <= 0.30) &
        (~is_crash)
    )

    # === 3. BEAR 判定（3 条件 AND，修复 A3）===
    is_bear = (
        (close < ma60) &
        (ma20 < ma60) &
        (pct_change_20d <= -0.05) &
        (~is_crash)
    )

    # === 4. 状态赋值 ===
    state = pd.Series("SIDEWAYS", index=df.index, dtype=object)
    state[is_crash] = "CRASH"
    state[is_bull & (~is_crash)] = "BULL"
    state[is_bear & (~is_crash) & (~is_bull)] = "BEAR"

    # === 5. Fallback 规则（修复 [v8.5] H3: 状态边界不连通）===
    # 上述三态交集存在空集（如涨幅=4.9%但价格突破 MA60+5%，三态都不命中）
    # 对三态均不命中的日期，按"涨幅最接近的归类"：
    #   - 涨幅 > 0  → BULL（偏多）
    #   - 涨幅 < 0  → BEAR（偏空）
    #   - 涨幅 = 0  → SIDEWAYS
    none_matched = (~is_crash) & (~is_bull) & (~is_bear)
    pct_change_20d_safe = pct_change_20d.fillna(0)
    state[none_matched & (pct_change_20d_safe > 0)] = "BULL"
    state[none_matched & (pct_change_20d_safe < 0)] = "BEAR"
    state[none_matched & (pct_change_20d_safe == 0)] = "SIDEWAYS"

    return pd.DataFrame({
        "state": state,
        "realized_vol_20d": realized_vol_20d,
        "drawdown_5d": drawdown_5d,
        "drawdown_20d": drawdown_20d
    })
```

## 4.5 状态迟滞机制

**问题**：原始状态分类器可能在 BULL / SIDEWAYS 之间频繁切换。
**解决**：连续 N 日满足 + 切换后冷却期。

```python
# regime/hysteresis.py
import pandas as pd
from typing import Optional

def apply_hysteresis(
    state: pd.Series,
    min_duration: int = 3,
    cooldown: int = 5
) -> pd.Series:
    """状态迟滞机制（修复 [v8.3] B4: 用交易日而非索引位置）

    Args:
        state: 原始状态序列（index 通常为日期索引）
        min_duration: 连续 N 日满足才切换（默认 3）
        cooldown: 切换后冷却期（默认 5 个**交易日**）

    Returns:
        Series: 加入迟滞后的状态

    修复说明：
    - 旧版用 `i - last_switch_idx < cooldown` 是索引差，遇到停牌/节假日时
      5 个索引位置 ≠ 5 个交易日，会导致冷却期不准确。
    - 新版调用 np.busday_count 计算实际交易日差。
    """
    result = [state.iloc[0]]
    candidate = state.iloc[0]
    candidate_count = 0
    last_switch_date = None  # 修复 B4: 用日期而非索引

    for i in range(1, len(state)):
        proposed = state.iloc[i]
        current_date = state.index[i]

        # 冷却期内保持现状（修复 C9: 冷却期只防"刚切完就切回"，
        # 如果新候选与当前状态相反，但冷却期已过，仍需迟滞确认）
        if last_switch_date is not None:
            # 修复 B4: 用实际交易日差（不是索引差）
            trading_days_since_switch = np.busday_count(
                last_switch_date.date(),
                current_date.date()
            )
            if trading_days_since_switch < cooldown:
                # 但 CRASH 状态特殊：冷却期内也允许立即进入
                if proposed == "CRASH":
                    result.append("CRASH")
                    last_switch_date = current_date
                    continue
                result.append(result[-1])
                continue

        if proposed == result[-1]:
            # 维持当前状态
            result.append(proposed)
            candidate = proposed
            candidate_count = 0
        else:
            # 候选新状态
            if proposed == candidate:
                candidate_count += 1
            else:
                candidate = proposed
                candidate_count = 1

            if candidate_count >= min_duration:
                # 确认切换
                result.append(proposed)
                last_switch_date = current_date  # 修复 B4
                candidate = proposed
                candidate_count = 0
            else:
                result.append(result[-1])

    return pd.Series(result, index=state.index, name="regime_confirmed")
```

### 4.5.1 急速 CRASH 例外处理

CRASH 必须**立即响应**（不等待 N 日），且**不进入冷却期**：

```python
def apply_hysteresis_with_crash_override(
    state: pd.Series,
    min_duration: int = 3,
    cooldown: int = 5
) -> pd.Series:
    """带 CRASH 例外的状态迟滞"""
    result = [state.iloc[0]]
    candidate = state.iloc[0]
    candidate_count = 0
    last_switch_idx = -999

    for i in range(1, len(state)):
        proposed = state.iloc[i]

        # CRASH 立即切换（无视冷却期）
        if proposed == "CRASH":
            result.append("CRASH")
            last_switch_idx = i
            candidate = "CRASH"
            candidate_count = 0
            continue

        # 冷却期内保持现状
        if i - last_switch_idx < cooldown:
            result.append(result[-1])
            continue

        if proposed == result[-1]:
            result.append(proposed)
            candidate = proposed
            candidate_count = 0
        else:
            if proposed == candidate:
                candidate_count += 1
            else:
                candidate = proposed
                candidate_count = 1

            if candidate_count >= min_duration:
                result.append(proposed)
                last_switch_idx = i
                candidate = proposed
                candidate_count = 0
            else:
                result.append(result[-1])

    return pd.Series(result, index=state.index, name="regime_confirmed")
```

## 4.6 震荡下行检测

**震荡下行 ≠ 趋势下跌 ≠ 震荡市**：
- 趋势下跌：单边急跌
- 震荡市：横盘震荡，重心不变
- **震荡下行**：MA60 走平或微跌，每天小阴小阳但重心持续下移

```python
# regime/choppy_bear.py
import pandas as pd
import numpy as np

def detect_choppy_bear(
    df: pd.DataFrame,
    cum_ret_th: float = -0.05,         # 60 日累计跌幅下限（默认 -5%，必须小于此值）
    cum_ret_upper: float = -0.20,      # 60 日累计跌幅上限（修复 [v8.4] B2: -20%，超过则归为崩盘）
    volatility_th: float = 0.18,        # 60 日波动率上限（默认 18%）
    # 修复 B1: 0.5%/月 = 0.025%/日（按 20 日月）= 0.00025/日
    # ATOS-des.md 原文 "0.02%/日" 是错的；按 0.5%/月 / 20 日 = 0.025%/日 = 0.00025 比率
    ma60_slope_th: float = 0.00025,     # MA60 20 日斜率绝对值阈值（修复 B1）
    score_threshold: int = 3            # 触发分数阈值
) -> dict:
    """震荡下行检测（4 维）

    Args:
        df: 必须包含 MA20, MA60, close 列
        cum_ret_th: 60 日累计跌幅阈值（小于此值）
        volatility_th: 60 日年化波动率上限
        ma60_slope_th: MA60 的 20 日斜率绝对值上限
        score_threshold: 触发分数阈值（4 个条件满足几个）

    Returns:
        dict: {
            "is_choppy_bear": bool,
            "score": int,
            "conditions": dict,
            "metrics": dict
        }
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    log_ret = np.log(close / close.shift(1))

    # 维度 1：60 日累计跌幅（修复 [v8.4] B2: 加 cum_ret_upper 上界）
    cum_ret_60d = close.iloc[-1] / close.iloc[-60] - 1
    cond_1 = (cum_ret_60d < cum_ret_th) and (cum_ret_60d > cum_ret_upper)
    # 等价于：-20% < cum_ret_60d < -5%

    # 维度 2：60 日波动率低
    vol_60d = log_ret.rolling(60).std().iloc[-1] * np.sqrt(252)
    cond_2 = vol_60d < volatility_th

    # 维度 3：MA60 走平（修复 B3-05: 20 日斜率，与策略文档 §5.1 一致）
    # [v8.4] B11 注释说明：iloc[-21] 是 21 日前的值，与 iloc[-1] 差 20 日窗口
    # 所以窗口 = 20 日 ✓
    ma60_20d_ago = ma60.iloc[-21] if len(ma60) >= 21 else ma60.iloc[0]
    ma60_slope = (ma60.iloc[-1] - ma60_20d_ago) / ma60_20d_ago
    # 修复 C10: 走平或微跌都算（与策略文档 §5.1 一致）
    cond_3 = abs(ma60_slope) < ma60_slope_th

    # 维度 4：MA20 < MA60
    cond_4 = ma20.iloc[-1] < ma60.iloc[-1]

    conditions = {
        "cum_ret_60d_negative": cond_1,
        "low_volatility": cond_2,
        "ma60_flat_or_down": cond_3,
        "ma20_below_ma60": cond_4
    }

    score = sum(conditions.values())
    is_choppy_bear = score >= score_threshold

    return {
        "is_choppy_bear": is_choppy_bear,
        "score": score,
        "conditions": conditions,
        "metrics": {
            "cum_ret_60d": cum_ret_60d,
            "vol_60d": vol_60d,
            "ma60_slope": ma60_slope,
            "ma20_vs_ma60": (ma20.iloc[-1] / ma60.iloc[-1] - 1) if ma60.iloc[-1] > 0 else 0
        }
    }
```

## 4.7 综合状态层（叠加震荡下行）

```python
# regime/combined.py
import pandas as pd


def compute_combined_regime(
    regime_state: pd.Series,
    choppy_bear: pd.Series,
    choppy_bear_grace_days: int = 3,  # 修复 [v8.5] D7: 延后撤销天数
) -> pd.DataFrame:
    """综合状态（市场状态 + 震荡下行叠加，修复 [v8.5] D7）

    Args:
        regime_state: 经迟滞后的市场状态序列
        choppy_bear: 每日震荡下行检测结果（bool）
        choppy_bear_grace_days: 切换到 BULL 后延后撤销天数（修复 D7，默认 3）

    Returns:
        DataFrame with columns: [state, choppy_bear, effective_state, target_position, mode_pnl, transition_position]

    修复说明（D7）：原文档"状态切换时专项规则瞬间撤销"会导致仓位从 20% 跳到 100%。
    修正：
    - 切到 BULL：专项规则延后 choppy_bear_grace_days 天撤销（线性插值）
    - 切到 CRASH：专项规则立即撤销（CRASH 强制空仓）
    - 切到 BEAR/SIDEWAYS：专项规则延续
    """
    df = pd.DataFrame({
        "state": regime_state,
        "choppy_bear": choppy_bear
    })

    # 计算 choppy_bear 生效期（修复 D7: 延后撤销逻辑）
    # choppy_bear_active = True 当：
    #   - choppy_bear == True（基本条件）
    #   - 或 choppy_bear 刚变 False 且 state == BULL 且仍在 grace_days 内
    #   - 或 state == CRASH（强制撤销）
    choppy_bear_active = df["choppy_bear"].copy()

    # 检测 choppy_bear 变 False 的位置 + 当时 state
    for i in range(1, len(df)):
        if df["choppy_bear"].iloc[i] == False and df["choppy_bear"].iloc[i-1] == True:
            # choppy_bear 刚结束
            current_state = df["state"].iloc[i]
            if current_state == "CRASH":
                # 切到 CRASH：立即撤销
                choppy_bear_active.iloc[i] = False
            elif current_state == "BULL":
                # 切到 BULL：延后撤销（grace_days 内仍激活）
                end_idx = min(i + choppy_bear_grace_days, len(df))
                choppy_bear_active.iloc[i:end_idx] = True
            # BEAR/SIDEWAYS：保持 choppy_bear_active = False（choppy_bear 已经 False）

    df["choppy_bear_active"] = choppy_bear_active

    # effective_state：用于决定参数
    df["effective_state"] = np.where(
        df["choppy_bear_active"],
        "CHOPPY_BEAR",
        df["state"]
    )

    # 目标仓位（基础值）
    base_position = {
        "BULL": 0.85,
        "SIDEWAYS": 0.55,
        "BEAR": 0.15,
        "CRASH": 0.05,
        "CHOPPY_BEAR": 0.15  # 与 BEAR 类似
    }
    df["base_target_position"] = df["effective_state"].map(base_position)

    # 修复 D7: 延后撤销期间，仓位线性插值
    # 检测 choppy_bear_active 刚激活的位置（从 CHOPPY_BEAR → BULL 切换）
    df["transition_position"] = df["base_target_position"]  # 默认值
    for i in range(1, len(df)):
        # 检查是否从 choppy_bear 转入 BULL
        if (df["choppy_bear"].iloc[i] == False and
            df["choppy_bear"].iloc[i-1] == True and
            df["state"].iloc[i] == "BULL"):
            # 延后期内：从 0.15 (CHOPPY_BEAR) 线性升至 0.85 (BULL)
            for day_offset in range(choppy_bear_grace_days):
                idx = min(i + day_offset, len(df) - 1)
                if df["choppy_bear_active"].iloc[idx]:
                    # 线性插值
                    ratio = (day_offset + 1) / (choppy_bear_grace_days + 1)
                    df.loc[df.index[idx], "transition_position"] = (
                        0.15 + (0.85 - 0.15) * ratio
                    )

    df["target_position"] = df["transition_position"]

    # mode_pnl：模式期累计收益占位
    df["mode_pnl"] = 0.0

    return df


def is_choppy_bear_over(
    choppy_bear: pd.Series,
    cumulative_pnl: pd.Series,
    close: pd.Series,
    vol_ratio: pd.Series,
    lookback: int = 5,
    max_days: int = 20,  # 修复 [v8.5] D6: 40 → 20 日
    loss_threshold: float = -0.05,  # 修复 [v8.5] D6: 模式期亏损阈值
    drawdown_expansion: int = 2,     # 修复 [v8.5] D6: 连续日数
    drawdown_expansion_th: float = -0.05,  # 修复 [v8.5] D6: 累计跌幅扩大阈值
) -> bool:
    """震荡下行退出条件（修复 [v8.5] D6: 4 个退出条件）

    修复说明：策略文档 §5.3 描述"累计收益 > 0"语义不明。
    现明确为：**组合净值从进入 CHOPPY_BEAR 起的累计变化**

    退出条件（任一满足，修复 D6）：
    1. **反弹退出**：累计收益 > 0 **且** 放量大阳线（涨幅 > 2% 且 量比 > 1.5）
    2. **亏损阈值退出**（D6 新增）：模式期累计亏损 > loss_threshold（默认 5%）
    3. **反弹破败退出**（D6 新增）：连续 N 日累计跌幅扩大
    4. **硬退出**（D6 修复）：持续 max_days 个交易日（**40 → 20**）

    Args:
        choppy_bear: 震荡下行标记序列
        cumulative_pnl: 组合累计收益序列
        close: 收盘价
        vol_ratio: 量比
        lookback: 放量检测窗口
        max_days: 最长持续日数（修复 D6: 默认 20 日，原 40 日）
        loss_threshold: 亏损阈值（修复 D6 新增，默认 -5%）
        drawdown_expansion: 反弹破败连续日数（修复 D6 新增）
        drawdown_expansion_th: 反弹破败累计跌幅扩大阈值（修复 D6 新增）
    """
    if not choppy_bear.iloc[-1]:
        return False

    # 找到进入 CHOPPY_BEAR 的最近起点
    in_choppy = choppy_bear.values
    if not in_choppy.any():
        return False

    # 找到最后一个 True 的起点
    last_true_idx = np.where(in_choppy)[0][-1]
    start_idx = last_true_idx
    for i in range(last_true_idx, -1, -1):
        if not in_choppy[i]:
            start_idx = i + 1
            break

    # 条件 1: 反弹退出（累计收益 > 0 且 放量大阳线）
    if start_idx < len(cumulative_pnl):
        mode_pnl = (cumulative_pnl.iloc[-1] - cumulative_pnl.iloc[start_idx]
                    if start_idx > 0 else cumulative_pnl.iloc[-1])
        if mode_pnl > 0:
            # 检查放量大阳线
            recent_pct = close.pct_change(lookback).iloc[-1]
            recent_vol = vol_ratio.iloc[-lookback:].mean()
            if recent_pct > 0.02 and recent_vol > 1.5:
                return True

        # 条件 2: 亏损阈值退出（修复 D6 新增）
        if mode_pnl <= loss_threshold:
            return True

        # 条件 3: 反弹破败退出（修复 D6 新增）
        # 连续 N 日累计跌幅扩大（close 持续走低）
        if len(close) >= drawdown_expansion:
            recent_closes = close.iloc[-drawdown_expansion:]
            if (recent_closes.pct_change().sum() <= drawdown_expansion_th):
                return True

    # 条件 4: 硬退出（修复 D6: 40 → 20 日）
    duration_days = len(choppy_bear) - start_idx
    if duration_days > max_days:
        return True

    return False
```

## 4.8 完整调用流程

```python
# regime/__init__.py 或 run.py
def detect_full_regime(df: pd.DataFrame,
                       config) -> pd.DataFrame:
    """完整的 4 状态 + 震荡下行检测流程

    Args:
        df: 含 open/high/low/close/volume + 所有指标的 DataFrame
        config: StrategyConfig

    Returns:
        DataFrame: 完整的每日状态信息
    """
    # 1. 原始 4 状态
    regime_raw = detect_market_regime(
        df,
        bull_th=config.bull_threshold,
        bear_th=config.bear_threshold,
        crash_th=config.crash_threshold
    )

    # 2. 状态迟滞
    state_confirmed = apply_hysteresis_with_crash_override(
        regime_raw["state"],
        min_duration=config.min_duration,
        cooldown=config.cooldown_days
    )

    # 3. 震荡下行检测（向量化，修复 C40）
    # 旧版 O(n²) 循环：每 i 都 df.iloc[:i+1]，n=2400 时 ~580 万次重复检测，约 50s
    # 新版向量化：所有指标一次计算，rolling 判断
    choppy_bear = _detect_choppy_bear_vectorized(df, score_threshold=3)

    # 4. 综合状态（修复 [v8.5] D7: 传递 grace_days）
    grace_days = getattr(config, "choppy_bear_grace_days", 3)
    combined = compute_combined_regime(
        state_confirmed, choppy_bear, choppy_bear_grace_days=grace_days
    )

    return combined


def _detect_choppy_bear_vectorized(
    df: pd.DataFrame,
    cum_ret_th: float = -0.05,
    volatility_th: float = 0.18,
    ma60_slope_th: float = 0.00025,
    score_threshold: int = 3
) -> pd.Series:
    """震荡下行检测向量化版本（修复 C40: O(n²) → O(n)）

    旧版每 i 都重新计算所有 rolling 指标，n 越大越慢
    新版：先向量化算好所有指标，再 rolling 求和
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    log_ret = np.log(close / close.shift(1))

    # 向量化计算
    cum_ret_60d = close / close.shift(60) - 1
    vol_60d = log_ret.rolling(60).std() * np.sqrt(252)
    ma60_slope = (ma60 - ma60.shift(10)) / ma60.shift(10)

    # 4 维条件
    cond_1 = cum_ret_60d < cum_ret_th
    cond_2 = vol_60d < volatility_th
    cond_3 = ma60_slope.abs() < ma60_slope_th
    cond_4 = ma20 < ma60

    # 求和（满足几个条件）
    score = (
        cond_1.fillna(False).astype(int) +
        cond_2.fillna(False).astype(int) +
        cond_3.fillna(False).astype(int) +
        cond_4.fillna(False).astype(int)
    )

    return (score >= score_threshold).fillna(False)
```

## 4.9 参数配置

```yaml
# config/params.yaml
regime:
  bull_threshold: 70
  bear_threshold: 30
  crash_threshold: 15
  crash_volatility: 0.35
  crash_5d_drawdown: -0.08
  crash_20d_drawdown: -0.15

  # 迟滞
  min_duration: 3         # 连续 3 日才切换
  cooldown_days: 5        # 切换后 5 日冷却

  # 震荡下行
  choppy_bear:
    cum_ret_th: -0.05     # 60 日累计跌 5%+
    volatility_th: 0.18   # 年化波动率 < 18%
    ma60_slope_th: 0.00025  # MA60 斜率 < 0.5%/月 = 0.025%/日（修复 B1）
    score_threshold: 3     # 4 维满足 3 维
```

## 4.10 测试

```python
# tests/test_regime.py
import pytest
import pandas as pd
import numpy as np
from regime.market_regime import detect_market_regime
from regime.hysteresis import apply_hysteresis, apply_hysteresis_with_crash_override
from regime.choppy_bear import detect_choppy_bear


@pytest.fixture
def bull_market_df():
    """构造牛市数据"""
    np.random.seed(42)
    n = 250
    close = pd.Series(np.cumsum(np.random.randn(n) * 0.01) + 100)
    high = close + 1
    low = close - 1
    df = pd.DataFrame({"close": close, "high": high, "low": low})
    # 手动计算指标
    df["MA20"] = close.rolling(20).mean()
    df["MA60"] = close.rolling(60).mean()
    df["MA120"] = close.rolling(120).mean()
    df["MACD"] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df["PDI"] = 30
    df["NDI"] = 20
    df["ADX"] = 30
    return df


def test_bull_state_detection(bull_market_df):
    """牛市应被识别为 BULL"""
    result = detect_market_regime(bull_market_df)
    assert "BULL" in result["state"].values


def test_hysteresis_prevents_frequent_switch():
    """迟滞应防止频繁切换"""
    states = pd.Series(["BULL"] * 5 + ["SIDEWAYS"] * 3 + ["BULL"] * 5)
    result = apply_hysteresis(states, min_duration=3, cooldown=5)
    # 不应频繁切换
    switch_count = (result != result.shift(1)).sum()
    assert switch_count <= 2  # 最多 2 次切换


def test_crash_override():
    """CRASH 应立即切换"""
    states = pd.Series(["BULL"] * 5 + ["CRASH"] + ["BULL"] * 5)
    result = apply_hysteresis_with_crash_override(states, min_duration=3, cooldown=5)
    assert result.iloc[5] == "CRASH"  # 立即响应


def test_choppy_bear_detection():
    """震荡下行应正确检测"""
    # 构造震荡下行数据：MA60 走平，60 日跌 5-20%
    np.random.seed(42)
    n = 100
    close = pd.Series(100 + np.linspace(-15, 0, n) + np.random.randn(n) * 0.3)
    df = pd.DataFrame({
        "close": close,
        "MA20": close.rolling(20).mean(),
        "MA60": close.rolling(60).mean()
    })
    result = detect_choppy_bear(df)
    assert "is_choppy_bear" in result
    assert "score" in result
    # 满足 3 维条件
    assert result["score"] >= 3
```

## 4.11 状态机可视化

```
                    CRASH
                      ↓ (立即)
[BULL] ←─迟滞 3 日─→ [SIDEWAYS] ←─迟滞 3 日─→ [BEAR]
   ↑                                              ↓
   └──────── 冷却 5 日 + 迟滞 3 日 ──────────────┘
   
叠加：CHOPPY_BEAR (在 BEAR/SIDEWAYS 上叠加，不改变 state)
```

## 4.12 性能

- 4 状态分类：~10ms / 2400 行
- 震荡下行检测（每日）：~50ms / 2400 行
- 完整流程：~100ms

性能瓶颈在**每日震荡下行检测**的滚动计算。可优化：
- 用 `df.rolling().apply()` 替代循环
- 缓存中间结果

## 4.13 已知限制

| 限制 | 原因 | 解决 |
|---|---|---|
| MA120 需要 120 日数据 | rolling 计算需要历史 | 早期日标记为 SIDEWAYS |
| ADX 早期数据不准 | Wilder 平滑需要 warmup | 至少 50 日后开始判定 |
| 震荡下行有滞后 | 4 维检测全用历史数据 | 可接受，是特性不是 bug |