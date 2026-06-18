"""市场状态识别 - 4 状态分类器（布尔规则版）"""
import numpy as np
import pandas as pd


def detect_market_regime(
    df: pd.DataFrame,
    crash_5d_drawdown: float = -0.08,
    crash_20d_drawdown: float = -0.15,
    crash_volatility_th: float = 0.35,
    adx_bull_th: float = 0.0,  # ATOS2 v2: 0=禁用, ADX/50 > 此值才算 BULL
    rsi_bear_th: float = 100.0,  # ATOS2 v2: 100=禁用, RSI < 此值才算 BEAR
    crash_volume_spike: float = 2.0,  # ATOS6 v1
) -> pd.DataFrame:
    """4 状态市场分类器（布尔规则版）

    严格按 ATOS-des.md §2.1 布尔规则判定：

    BULL（同时满足 4 条件）：
    ① 收盘价 > MA60
    ② MA20 > MA60
    ③ 近 20 日涨幅 >= 5%
    ④ 20 日年化波动率 <= 30%

    BEAR（同时满足 3 条件）：
    ① 收盘价 < MA60
    ② MA20 < MA60
    ③ 近 20 日涨幅 <= -5%
    ④ 不属于 CRASH

    CRASH（OR 关系）：
    ① 近 5 日跌幅 >= 8% 或 近 20 日跌幅 >= 15%
    ② 20 日波动率 > 35% 且 5 日跌幅 > 5%（可选加速）

    SIDEWAYS：以上都不满足
    """
    close = df["close"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]

    log_ret = np.log(close / close.shift(1))
    realized_vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    pct_change_20d = close / close.shift(20) - 1
    drawdown_5d = close / close.shift(5) - 1
    drawdown_20d = close / close.shift(20) - 1

    # 1. CRASH 判定（最高优先级，OR 关系；ATOS6 v1 加 panic volume）
    crash_basic = (drawdown_5d <= crash_5d_drawdown) | (drawdown_20d <= crash_20d_drawdown)
    crash_acceleration = (realized_vol_20d > crash_volatility_th) & (drawdown_5d < -0.05)
    # ATOS6 v1：成交额暴增（恐慌盘）
    if "amount" in df.columns and "amount" in df.columns:
        amt_ratio = df["amount"] / df["amount"].rolling(20).mean()
        crash_volume = (amt_ratio > crash_volume_spike) & (drawdown_5d < -0.03)
    else:
        crash_volume = pd.Series(False, index=df.index)
    is_crash = (crash_basic | crash_acceleration | crash_volume).fillna(False)

    # 2. BULL 判定（4-6 条件 AND，ATOS2 v2 可选 ADX）
    is_bull = (
        (close > ma60) &
        (ma20 > ma60) &
        (pct_change_20d >= 0.05) &
        (realized_vol_20d <= 0.30) &
        (~is_crash)
    ).fillna(False)

    # 3. BEAR 判定（3-4 条件 AND，ATOS2 v2 可选 RSI）
    is_bear = (
        (close < ma60) &
        (ma20 < ma60) &
        (pct_change_20d <= -0.05) &
        (~is_crash)
    ).fillna(False)

    # 4. 状态赋值
    state = pd.Series("SIDEWAYS", index=df.index, dtype=object)
    state[is_crash] = "CRASH"
    state[is_bull & (~is_crash)] = "BULL"
    state[is_bear & (~is_crash) & (~is_bull)] = "BEAR"

    # 5. Fallback：三态均不命中时按涨幅方向归类
    none_matched = (~is_crash) & (~is_bull) & (~is_bear)
    pct_safe = pct_change_20d.fillna(0)
    state[none_matched & (pct_safe > 0)] = "BULL"
    state[none_matched & (pct_safe < 0)] = "BEAR"
    state[none_matched & (pct_safe == 0)] = "SIDEWAYS"

    return pd.DataFrame({
        "state": state,
        "realized_vol_20d": realized_vol_20d,
        "drawdown_5d": drawdown_5d,
        "drawdown_20d": drawdown_20d,
    })
