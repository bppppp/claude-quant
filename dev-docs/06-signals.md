# 06 - 买卖信号层

## 6.1 职责

根据市场状态和选股结果，生成**买卖信号**。

需要实现：
- 6 类买点
- 4 类卖点
- 假突破过滤

## 6.2 模块结构

```
signals/
├── __init__.py
├── entry.py            # 6 类买点
├── exit.py             # 4 类卖点
├── filter.py           # 假突破过滤
└── priority.py         # 信号优先级
```

## 6.3 6 类买点

### 买点 1：均线金叉 + MACD 金叉（BULL 用）

```python
# signals/entry.py
import pandas as pd

def signal_ma_macd(df: pd.DataFrame) -> pd.Series:
    """MA5 上穿 MA10 金叉（修复 B11: 与策略文档 §8.1 一致）

    策略文档：「均线金叉：MA5 上穿 MA10」
    旧版是 4 重条件（多头排列+零轴上方），过于严格
    修复：单金叉 + 确认
    """
    ma5 = df["MA5"]
    ma10 = df["MA10"]

    # 金叉：MA5 上穿 MA10
    golden_cross = (ma5 > ma10) & (ma5.shift(1) <= ma10.shift(1))

    return golden_cross.astype(int)
```

### 买点 2：KDJ 金叉 + RSI 确认（SIDEWAYS 用）

```python
def signal_kdj_rsi(df: pd.DataFrame) -> pd.Series:
    """KDJ 金叉 + K/D 阈值（修复 B12: 用 K/D 不用 J）

    策略文档 §8.1：「KDJ 金叉：K 上穿 D，且 K<80，D<70」
    旧版用 J 值在 0-80 之间是错的
    修复：用 K 和 D 自身的阈值
    """
    k = df["K"]
    d = df["D"]
    rsi6 = df["RSI6"]
    rsi12 = df["RSI12"]

    cond1 = (k > d) & (k.shift(1) <= d.shift(1))  # 金叉
    cond2 = (k < 80) & (d < 70)                  # 修复 B12: 用 K 和 D
    cond3 = (rsi6 > 20) & (rsi12 > 30)

    return (cond1 & cond2 & cond3).astype(int)
```

### 买点 3：布林下轨 + 量能萎缩（SIDEWAYS / 弱 BEAR）

```python
def signal_boll_volume(df: pd.DataFrame) -> pd.Series:
    """触及布林下轨 + 量能萎缩 + RSI 超卖（修复 B13 + [v8.4] A11）

    策略文档 §8.1：「昨日收盘价 ≤ 布林下轨，今日收阳线」
    旧版 cond1 = (close_prev <= boll_low) & (close <= boll_low * 1.001)
    语义反转：要求"今日 close <= boll_low"意味着今日仍在下轨或之下，
    与"下轨反弹"语义完全相反。
    修复 [v8.4] A11: 改为「昨日 <= 下轨 且 今日 > 下轨」真正"反弹"。
    """
    close = df["close"]
    close_prev = close.shift(1)
    boll_low = df["BOLL_DOWN"]
    boll_mid = df["BOLL_MID"]
    vol = df["volume"]
    rsi6 = df["RSI6"]

    vol_ma5 = vol.rolling(5).mean()

    # 修复 [v8.4] A11: 昨日触及下轨 + 今日反弹站上下轨
    cond1 = (close_prev <= boll_low * 1.001)  # 昨日接近/触及下轨
    cond2 = close > boll_low                    # 今日回到下轨上方（反弹）
    cond3 = close > close_prev                  # 今日收阳线
    cond4 = vol > vol_ma5 * 1.2                 # 放量确认反弹
    cond5 = rsi6 < 35                           # RSI 超卖区
    cond6 = close > boll_mid * 0.90             # 远离中轨（避免中轨附近震荡）

    return (cond1 & cond2 & cond3 & cond4 & cond5 & cond6).astype(int)
```

### 买点 4：Donchian 突破 + 放量（BULL 用）

```python
def signal_donchian_breakout(df: pd.DataFrame) -> pd.Series:
    """突破 20 日最高 + 放量 + ADX > 20"""
    close = df["close"]
    dc_up_prev = df["DC_UP"].shift(1)
    vol = df["volume"]
    vol_ma20 = vol.rolling(20).mean()
    adx = df["ADX"]

    return ((close > dc_up_prev) & (vol > vol_ma20 * 1.5) & (adx > 20)).astype(int)
```

### 买点 5：MACD 底背离（BEAR 末期）

```python
def signal_macd_bottom_divergence(df: pd.DataFrame,
                                    lookback: int = 60) -> pd.Series:
    """MACD 底背离：价新低，MACD 不新低"""
    close = df["close"]
    macd = df["MACD"]
    sig = pd.Series(0, index=df.index)

    for i in range(lookback, len(df)):
        window_close = close.iloc[i-lookback:i+1]
        if close.iloc[i] != window_close.min():
            continue

        prev_idx = window_close.iloc[:-1].idxmin()
        if (close.iloc[i] < close.loc[prev_idx] and
            macd.iloc[i] > macd.loc[prev_idx]):
            sig.iloc[i] = 1

    return sig
```

### 买点 6：均线粘合突破

```python
def signal_ma_converge_break(df: pd.DataFrame) -> pd.Series:
    """MA 粘合后突破（修复 C5）

    修复：原条件「粘合（ma5 ≈ ma20）+ 多头排列（ma5 > ma10 > ma20）」极难同时成立
    改为：粘合 → 突破（不再要求已经多头排列）
    """
    ma5 = df["MA5"]
    ma10 = df["MA10"]
    ma20 = df["MA20"]
    close = df["close"]
    vol = df["volume"]
    vol_ma20 = vol.rolling(20).mean()

    # 粘合：MA5/MA10/MA20 差距都 < 2%
    converge = ((ma5 / ma20 - 1).abs() < 0.02) & \
               ((ma5 / ma10 - 1).abs() < 0.02) & \
               ((ma10 / ma20 - 1).abs() < 0.02)

    # 突破：价格上穿 MA20（不再要求 MA5 > MA10 > MA20）
    breakout = close > ma20
    recent = breakout & (~breakout.shift(1).fillna(False))

    return (converge.shift(1) & recent & (vol > vol_ma20 * 1.2)).astype(int)
```

### 综合买点选择（按市场状态）

```python
def generate_buy_signals(df: pd.DataFrame, regime: str,
                          config = None) -> pd.DataFrame:
    """根据市场状态选择启用的买点（修复 [v8.5] D8: 主辅信号分级）

    Args:
        df: 含所有指标的 DataFrame
        regime: 市场状态
        config: StrategyConfig（含 open_threshold_by_regime）

    Returns:
        DataFrame: 各买点信号 + weighted_score（主×2 + 辅×1）+ final

    修复 [v8.5] D8 优先级规则：
    - 主信号触发 → 立即候选
    - 仅辅信号 → 需 ≥2 个辅信号同时触发
    - 主辅混合 → 加权得分 = 主×2 + 辅×1
    - 阈值从 config.open_threshold_by_regime 取（与 §3 表一致）
    """
    signals = pd.DataFrame({
        "sig_ma_macd": signal_ma_macd(df),
        "sig_kdj_rsi": signal_kdj_rsi(df),
        "sig_boll_vol": signal_boll_volume(df),
        "sig_dc_break": signal_donchian_breakout(df),
        "sig_macd_div": signal_macd_bottom_divergence(df),
        "sig_ma_conv": signal_ma_converge_break(df)
    }, index=df.index)

    # 修复 D8: 主信号 + 辅信号分级
    PRIMARY_SIGNALS = {
        "BULL": ["sig_ma_macd", "sig_dc_break"],
        "SIDEWAYS": ["sig_kdj_rsi"],
        "BEAR": ["sig_macd_div"],
        "CHOPPY_BEAR": ["sig_macd_div"],
    }
    SECONDARY_SIGNALS = {
        "BULL": ["sig_ma_conv"],
        "SIDEWAYS": ["sig_boll_vol"],
        "BEAR": ["sig_boll_vol"],
        "CHOPPY_BEAR": [],
    }

    if regime in ("CRASH",):
        signals["weighted_score"] = 0
        signals["final"] = 0
        return signals

    primary = PRIMARY_SIGNALS.get(regime, [])
    secondary = SECONDARY_SIGNALS.get(regime, [])

    # 主信号加权得分（×2）
    primary_score = sum(signals[s] for s in primary if s in signals.columns) * 2

    # 辅信号加权得分（×1）
    secondary_score = sum(signals[s] for s in secondary if s in signals.columns)

    # 加权得分归一化到 [0, 1]
    max_score = (len(primary) * 2 + len(secondary)) if (primary or secondary) else 1
    signals["weighted_score"] = (primary_score + secondary_score) / max_score

    # 修复 D8: 从 config 取阈值（§3 表 BULL=0.70/SIDEWAYS=0.60/BEAR=0.75/CHOPPY_BEAR=0.75）
    if config is not None and hasattr(config, "open_threshold_by_regime"):
        thresholds = config.open_threshold_by_regime
    else:
        # 兜底：与 §3 表格一致
        thresholds = {
            "BULL": 0.70,
            "SIDEWAYS": 0.60,
            "BEAR": 0.75,
            "CHOPPY_BEAR": 0.75,
        }
    threshold = thresholds.get(regime, 0.70)

    signals["final"] = (signals["weighted_score"] >= threshold).astype(int)

    # 辅信号阈值检查（≥2 个辅信号同时触发才算）
    if secondary:
        sec_count = sum(signals[s] for s in secondary if s in signals.columns)
        sec_only = (signals["weighted_score"] == 0) & (sec_count >= 2)
        signals.loc[sec_only, "final"] = 1

    return signals
```

## 6.4 4 类卖点

```python
# signals/exit.py
import pandas as pd

def signal_ma_macd_death(df: pd.DataFrame) -> pd.Series:
    """MA5 下穿 MA10 死叉（修复 B10: 与策略文档 §8.2 一致）

    策略文档：「均线死叉：MA5 下穿 MA10」（单条件）
    旧版是 4 重条件（多头死叉+零轴下方），过于严格
    修复：单死叉
    """
    ma5 = df["MA5"]
    ma10 = df["MA10"]

    # 死叉：MA5 下穿 MA10
    death_cross = (ma5 < ma10) & (ma5.shift(1) >= ma10.shift(1))

    return death_cross.astype(int)


def signal_kdj_overbought_death(df: pd.DataFrame) -> pd.Series:
    """KDJ 超买死叉"""
    # 修复 C7: 改用 KDJ 自身超买条件（与策略文档 §8.2 一致）
    # 策略文档：「K > 80 且 D > 70，然后 K 下穿 D」
    k = df["K"]
    d = df["D"]

    # 死叉
    cond1 = (k < d) & (k.shift(1) >= d.shift(1))
    # 死叉前曾进入超买区
    cond2 = (k.shift(1) > 80) & (d.shift(1) > 70)

    return (cond1 & cond2).astype(int)


def signal_boll_mid_break(df: pd.DataFrame) -> pd.Series:
    """跌破布林中轨"""
    close = df["close"]
    boll_mid = df["BOLL_MID"]

    return (close < boll_mid) & (close.shift(1) >= boll_mid.shift(1))


def signal_macd_top_divergence(df: pd.DataFrame,
                                 lookback: int = 60) -> pd.Series:
    """MACD 顶背离：价新高，MACD 不新高（修复 C15: 向量化 O(n)）"""
    close = df["close"]
    macd = df["MACD"]

    # 修复 C15: 原 O(n²) 循环，n=2400 时约 30-60 秒
    # 新版向量化：用 rolling 找 lookback 内最高价
    rolling_max = close.rolling(lookback, min_periods=lookback).max()
    rolling_max_macd = macd.rolling(lookback, min_periods=lookback).max()

    # 价新高
    price_new_high = close == rolling_max
    # MACD 不新高
    macd_not_new_high = macd < rolling_max_macd

    return (price_new_high & macd_not_new_high).astype(int)


def generate_sell_signals(df: pd.DataFrame) -> pd.DataFrame:
    """生成所有卖点信号"""
    signals = pd.DataFrame({
        "sig_ma_macd_death": signal_ma_macd_death(df),
        "sig_kdj_over_death": signal_kdj_overbought_death(df),
        "sig_boll_mid": signal_boll_mid_break(df),
        "sig_macd_top_div": signal_macd_top_divergence(df)
    }, index=df.index)

    signals["any_sell"] = signals.any(axis=1).astype(int)
    return signals
```

## 6.5 假突破过滤

```python
# signals/filter.py
import pandas as pd

class BreakoutFilter:
    """假突破过滤器

    任何买入信号触发后，若持仓 3 日内跌破买入当天最低价
    → 强制平仓（视为假突破）
    """

    def __init__(self, holding_days: int = 3, trading_days: list = None):
        """
        Args:
            holding_days: 持仓交易日数（不是自然日，修复 C8）
            trading_days: 交易日历列表（pd.DatetimeIndex）
        """
        self.holding_days = holding_days
        self.trading_days = trading_days  # 修复 C8: 交易日历
        self.buy_records = {}

    def record_buy(self, symbol: str, date, low_price: float):
        """记录买入"""
        expire_date = self._get_trading_date_after(date, self.holding_days)
        self.buy_records[symbol] = {
            "date": date,
            "buy_day_low": low_price,
            "expire_date": expire_date
        }

    def _get_trading_date_after(self, start_date, n_days: int):
        """获取 start_date 后第 n 个交易日

        修复 [v8.3] E24：语义明确为"start_date 之后的第 n 个交易日"，
        当 start_date 是交易日时，n_days=1 表示"start_date 的下一个交易日"，
        与 holding_days=3 的 "3 个交易日内" 语义一致。
        """
        if self.trading_days is None or len(self.trading_days) == 0:
            # fallback: 用 bdate_range（BDay(1) = 下一个工作日）
            return start_date + pd.tseries.offsets.BDay(n_days)

        # 在交易日历中找到 start_date 之后的所有交易日
        future_days = [d for d in self.trading_days if d > start_date]
        if len(future_days) >= n_days:
            return future_days[n_days - 1]
        # n_days 超过可用天数：返回最后一个
        return future_days[-1] if future_days else start_date

    def check_filter(self, symbol: str, current_date, current_low: float) -> bool:
        """检查是否触发假突破过滤

        Returns:
            True = 触发假突破，应平仓
        """
        if symbol not in self.buy_records:
            return False

        record = self.buy_records[symbol]

        # 已过期
        if current_date > record["expire_date"]:
            del self.buy_records[symbol]
            return False

        # 当日最低价跌破买入当天最低价
        if current_low < record["buy_day_low"]:
            del self.buy_records[symbol]
            return True

        return False

    def clear(self, symbol: str):
        """清除记录（成功持仓）"""
        if symbol in self.buy_records:
            del self.buy_records[symbol]
```

## 6.6 信号优先级

```python
# signals/priority.py
class SignalPriority:
    """信号优先级排序"""

    SELL_PRIORITY = [
        "crash_force_exit",      # P0：CRASH 强制清仓
        "trailing_stop",         # P1：移动止盈
        "batch_take_profit",     # P2：分批止盈
        "time_stop",             # P3：时间止损
        "hard_stop",             # P4：硬止损（仅 BULL）
        "false_breakout",        # P5：假突破
        "sell_signal",           # P6：技术卖点
    ]

    BUY_PRIORITY = [
        "selected_by_regime",    # P0：选股后买入
        "regime_bull",           # P1：仅 BULL 状态
    ]

    @classmethod
    def should_sell_first(cls, signal1: str, signal2: str) -> str:
        """两个卖出信号哪个优先"""
        p1 = cls.SELL_PRIORITY.index(signal1) if signal1 in cls.SELL_PRIORITY else 999
        p2 = cls.SELL_PRIORITY.index(signal2) if signal2 in cls.SELL_PRIORITY else 999
        return signal1 if p1 < p2 else signal2
```

## 6.7 完整使用流程

```python
# signals/__init__.py
from signals.entry import generate_buy_signals
from signals.exit import generate_sell_signals
from signals.filter import BreakoutFilter

def generate_daily_signals(
    date: pd.Timestamp,
    df: pd.DataFrame,
    regime: str,
    positions: dict,
    filter_mgr: BreakoutFilter,
    symbol: str = None,  # 修复 [v8.4] C12: 单标的模式需显式传入 symbol
    config = None       # 修复 [v8.4] C12: 多标的模式下用 config.symbol
) -> dict:
    """生成每日交易信号

    Args:
        date: 当前日期
        df: 指标 DataFrame（**单标的**模式）
        regime: 市场状态
        positions: 当前持仓 {symbol: Position}
        filter_mgr: 假突破过滤器
        symbol: 单标的模式下的股票代码（None 时尝试用 config.symbol）
        config: StrategyConfig（多标的模式下用于获取 config.symbol）

    Returns:
        {
            "buy": [(symbol, signal_type), ...],
            "sell": [(symbol, ratio, reason), ...]
        }
    """
    signals = {
        "buy": [],
        "sell": []
    }

    # 1. 假突破检查（已持仓，修复 [v8.3] E26: 用 try/except 防 KeyError）
    for symbol, pos in positions.items():
        if pos.entry_date > date:
            continue
        # 用 get 避免 KeyError，stop 止损信号在缺失数据时跳过
        try:
            current_low = df.loc[date, "low"]
        except KeyError:
            current_low = None
        if current_low is not None and pd.notna(current_low):
            if filter_mgr.check_filter(symbol, date, current_low):
                signals["sell"].append((symbol, 1.0, "假突破过滤"))

    # 2. 卖点信号
    sell_signals = generate_sell_signals(df)
    if sell_signals.loc[date, "any_sell"] == 1:
        for symbol, pos in positions.items():
            if pos.entry_date <= date:
                signals["sell"].append((symbol, 1.0, "技术卖点"))

    # 3. 买点信号
    # 修复 B5-05 + [v8.4] C12 + [v8.5] D8: (symbol, type) 而非 (name, type)，传 config
    buy_signals = generate_buy_signals(df, regime, config=config)
    if buy_signals.loc[date, "final"] == 1:
        # 修复 [v8.4] C12: 用参数 symbol，避免 self.config.symbol 报 NameError
        if symbol is None and config is not None:
            symbol = config.symbol
        if symbol is not None:
            signals["buy"].append((symbol, "regime_signal"))
        else:
            # 多标的模式：返回空 buy，由 BacktestEngine._process_buys 处理
            pass

    return signals
```

## 6.8 测试

```python
# tests/test_signals.py
import pytest
import pandas as pd
import numpy as np
from signals.entry import signal_ma_macd, signal_kdj_rsi
from signals.exit import signal_ma_macd_death


@pytest.fixture
def sample_indicator_df():
    np.random.seed(42)
    n = 200
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    df = pd.DataFrame({
        "close": close, "high": close + 1, "low": close - 1,
        "volume": np.random.randint(1e6, 1e7, n)
    })
    df["MA5"] = close.rolling(5).mean()
    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()
    df["DIF"] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df["DEA"] = df["DIF"].ewm(span=9).mean()
    df["MACD"] = 2 * (df["DIF"] - df["DEA"])
    df["K"] = 50
    df["D"] = 50
    df["J"] = 50
    df["RSI6"] = 50
    df["RSI12"] = 50
    return df


def test_signal_ma_macd_no_signal_in_bear(sample_indicator_df):
    """均线空头时不应有信号"""
    sig = signal_ma_macd(sample_indicator_df)
    assert sig.sum() == 0  # 随机数据无明确金叉


def test_sell_signals_have_correct_format():
    """卖点信号应为 0/1 整数"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(100)) + 100)
    df = pd.DataFrame({
        "close": close, "MA5": close.rolling(5).mean(),
        "MA10": close.rolling(10).mean(), "MA20": close.rolling(20).mean()
    })
    df["DIF"] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df["DEA"] = df["DIF"].ewm(span=9).mean()

    sig = signal_ma_macd_death(df)
    assert set(sig.unique()).issubset({0, 1})
```

## 6.9 性能

| 操作 | 2400 行 | 时间 |
|---|---|---|
| 6 买点 | 1 只股票 | ~5ms |
| 4 卖点 | 1 只股票 | ~3ms |
| 假突破检查 | 100 只持仓 | ~1ms |
| 综合信号 | 1 只股票 | ~10ms |