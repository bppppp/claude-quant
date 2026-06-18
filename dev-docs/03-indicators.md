# 03 - 指标层（基于金玥数据）

## 3.1 职责

计算所有**技术分析指标**，作为上层（状态识别、选股、信号）的输入。

> **重要**：金玥数据**只提供 OHLCV + 均线 + 涨跌幅**，**不提供** MACD/KDJ/RSI/BOLL/ATR/OBV 等技术指标。
> 这些指标需要**在指标层自己计算**。

需要实现的 13 个核心指标（修复 B5: 与 overview 对齐）：
- 趋势类（4）：MA、MACD、DMI/ADX、均线粘合度
- 动量类（3）：KDJ、RSI、CCI
- 通道类（3）：BOLL、ATR、Donchian
- 量价类（3）：OBV、MFI、量比（VWAP 可选）

## 3.2 数据来源

金玥数据中已有的字段（直接使用）：
- `open, high, low, close, volume, amount`
- `MA5, MA10, MA20, MA30, MA60, MA120, MA250`（7 条均线）
- `pct_change, pct_change_3d, pct_change_6d, pct_change_10d, pct_change_25d`
- `turnover, vol_ratio, amplitude, is_limit_up`

需要**自己计算**的字段：
- MACD, KDJ, RSI, BOLL, ATR
- DMI/ADX, OBV, MFI, VWAP
- Donchian 通道
- 各种动量因子

## 3.3 模块结构

```
indicators/
├── __init__.py
├── base.py                 # 抽象基类 + 工具函数
├── trend.py                # MA, MACD, DMI
├── momentum.py             # KDJ, RSI, CCI
├── channels.py             # BOLL, ATR, Donchian
├── volume.py               # OBV, VWAP, MFI
└── pipeline.py             # 一键计算所有指标（带缓存）
```

## 3.4 基础工具

```python
# indicators/base.py
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Union


class BaseIndicator(ABC):
    """技术指标抽象基类"""

    @abstractmethod
    def calc(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

    def validate(self, df: pd.DataFrame) -> bool:
        required = ["open", "high", "low", "close", "volume"]
        return all(c in df.columns for c in required)


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder 平滑（用于 ADX、ATR）"""
    return series.ewm(alpha=1/period, adjust=False).mean()


def safe_divide(a: Union[pd.Series, float], b: Union[pd.Series, float],
                default: float = 0.0) -> Union[pd.Series, float]:
    """安全除法（避免除零）"""
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan).fillna(default)
    return a / b if b != 0 else default
```

### 3.4 设计原则

| 原则 | 实现 |
|---|---|
| 纯函数 | 所有 calc 函数只依赖入参 |
| 向量化 | 用 pandas/numpy 避免循环 |
| 一致接口 | 所有函数返回 `pd.DataFrame` 或 `pd.Series` |
| 不修改入参 | 操作前 `.copy()` |
| 容错性 | 异常输入返回空 Series |
| 缓存友好 | 计算结果可缓存到 `data/processed/` |
| 接受金玥字段 | MA 直接读 `MA60` 列，自己算 MACD 等 |

## 3.4 基础工具

```python
# indicators/base.py
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Union


class BaseIndicator(ABC):
    """技术指标抽象基类"""

    @abstractmethod
    def calc(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算指标"""
        pass

    def validate(self, df: pd.DataFrame) -> bool:
        """验证入参"""
        required = ["open", "high", "low", "close", "volume"]
        return all(c in df.columns for c in required)


def wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder 平滑（用于 ADX、ATR）"""
    return series.ewm(alpha=1/period, adjust=False).mean()


def safe_divide(a: Union[pd.Series, float], b: Union[pd.Series, float],
                default: float = 0.0) -> Union[pd.Series, float]:
    """安全除法（避免除零）"""
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan).fillna(default)
    return a / b if b != 0 else default
```

## 3.5 趋势类指标

### 3.5.1 移动平均线（MA）

```python
# indicators/trend.py
import pandas as pd

def calc_ma(close: pd.Series,
            periods: list[int] = [5, 10, 20, 60, 120, 250]) -> pd.DataFrame:
    """简单移动平均线（SMA）

    Args:
        close: 收盘价序列
        periods: 周期列表

    Returns:
        DataFrame，列名为 MA{period}
    """
    return pd.DataFrame({
        f"MA{p}": close.rolling(window=p, min_periods=1).mean()
        for p in periods
    })


def calc_ema(close: pd.Series,
             periods: list[int] = [5, 10, 20, 60]) -> pd.DataFrame:
    """指数移动平均线（EMA）

    Args:
        close: 收盘价序列
        periods: 周期列表

    Returns:
        DataFrame，列名为 EMA{period}
    """
    return pd.DataFrame({
        f"EMA{p}": close.ewm(span=p, adjust=False).mean()
        for p in periods
    })


def calc_ma_alignment(close: pd.Series,
                      fast: int = 5,
                      mid: int = 10,
                      slow: int = 20,
                      very_slow: int = 60) -> pd.Series:
    """均线排列强度

    计算：MA5/MA10/MA20/MA60 的多头排列程度
    - 1.0 = 完全多头排列（MA5 > MA10 > MA20 > MA60）
    - 0.0 = 完全空头排列
    - 0.5 = 混乱

    Returns:
        Series，值在 [0, 1]
    """
    ma_f = close.rolling(fast).mean()
    ma_m = close.rolling(mid).mean()
    ma_s = close.rolling(slow).mean()
    ma_vs = close.rolling(very_slow).mean()

    score = pd.Series(0.0, index=close.index)
    score += (ma_f > ma_m).astype(float) * 0.25
    score += (ma_m > ma_s).astype(float) * 0.25
    score += (ma_s > ma_vs).astype(float) * 0.25
    score += (ma_f > ma_s).astype(float) * 0.25

    return score


def calc_ma_convergence(close: pd.Series,
                         fast: int = 5,
                         mid: int = 10,
                         slow: int = 20) -> pd.Series:
    """均线粘合度

    衡量 MA5/MA10/MA20 之间的接近程度
    返回值越小表示越粘合（变盘点信号）

    Returns:
        Series，越小越粘合
    """
    ma_f = close.rolling(fast).mean()
    ma_m = close.rolling(mid).mean()
    ma_s = close.rolling(slow).mean()

    max_ma = pd.concat([ma_f, ma_m, ma_s], axis=1).max(axis=1)
    min_ma = pd.concat([ma_f, ma_m, ma_s], axis=1).min(axis=1)

    # 粘合度：(max - min) / mean
    return (max_ma - min_ma) / close
```

### 3.5.2 MACD

```python
def calc_macd(close: pd.Series,
              fast: int = 12,
              slow: int = 26,
              signal: int = 9) -> pd.DataFrame:
    """MACD 指标

    Args:
        close: 收盘价
        fast: 快线周期
        slow: 慢线周期
        signal: 信号线周期

    Returns:
        DataFrame with columns: [DIF, DEA, MACD]
        - DIF: 快慢线差
        - DEA: 信号线
        - MACD: 柱状图（DIF - DEA）的 2 倍
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_bar = (dif - dea) * 2

    return pd.DataFrame({
        "DIF": dif,
        "DEA": dea,
        "MACD": macd_bar
    })


def macd_golden_cross(macd_df: pd.DataFrame) -> pd.Series:
    """MACD 金叉信号（DIF 上穿 DEA）"""
    dif = macd_df["DIF"]
    dea = macd_df["DEA"]
    return ((dif > dea) & (dif.shift(1) <= dea.shift(1))).astype(int)


def macd_death_cross(macd_df: pd.DataFrame) -> pd.Series:
    """MACD 死叉信号（DIF 下穿 DEA）"""
    dif = macd_df["DIF"]
    dea = macd_df["DEA"]
    return ((dif < dea) & (dif.shift(1) >= dea.shift(1))).astype(int)
```

### 3.5.3 DMI / ADX

```python
def calc_dmi_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                 period: int = 14) -> pd.DataFrame:
    """DMI 趋向指标 + ADX 趋势强度

    Args:
        high, low, close: 最高、最低、收盘价
        period: 周期（默认 14）

    Returns:
        DataFrame with columns: [PDI, NDI, ADX, DX]
        - PDI: +DI（上升动向）
        - NDI: -DI（下降动向）
        - ADX: 平均趋向指数（趋势强度，> 25 为强趋势）
        - DX: 趋向指数
    """
    # True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # +DM / -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=close.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=close.index
    )

    # Wilder 平滑
    atr = wilder_smooth(tr, period)
    pdi = 100 * wilder_smooth(plus_dm, period) / atr
    ndi = 100 * wilder_smooth(minus_dm, period) / atr

    # DX / ADX
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    adx = wilder_smooth(dx.fillna(0), period)

    return pd.DataFrame({
        "PDI": pdi,
        "NDI": ndi,
        "DX": dx,
        "ADX": adx
    })
```

## 3.6 动量类指标

### 3.6.1 KDJ

```python
# indicators/momentum.py
import pandas as pd
import numpy as np

def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series,
             n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ 随机指标

    Args:
        high, low, close: 高、低、收
        n: RSV 周期
        m1: K 值平滑周期
        m2: D 值平滑周期

    Returns:
        DataFrame with columns: [K, D, J]
        - K: 快速确认线
        - D: 慢速确认线
        - J: 方向敏感线
    """
    # 修复 C14: 用 min_periods=n 而不是 1（避免早期单点数据污染）
    low_n = low.rolling(n, min_periods=n).min()
    high_n = high.rolling(n, min_periods=n).max()

    rsv = (close - low_n) / (high_n - low_n + 1e-9) * 100
    k = rsv.ewm(alpha=1/m1, adjust=False).mean()
    d = k.ewm(alpha=1/m2, adjust=False).mean()
    j = 3 * k - 2 * d

    return pd.DataFrame({"K": k, "D": d, "J": j})


def kdj_golden_cross(kdj_df: pd.DataFrame) -> pd.Series:
    """KDJ 金叉（K 上穿 D）"""
    k = kdj_df["K"]
    d = kdj_df["D"]
    return ((k > d) & (k.shift(1) <= d.shift(1))).astype(int)


def kdj_death_cross(kdj_df: pd.DataFrame) -> pd.Series:
    """KDJ 死叉（K 下穿 D）"""
    k = kdj_df["K"]
    d = kdj_df["D"]
    return ((k < d) & (k.shift(1) >= d.shift(1))).astype(int)
```

### 3.6.2 RSI

```python
def calc_rsi(close: pd.Series,
             periods: list[int] = [6, 12, 14, 24]) -> pd.DataFrame:  # 修复 B2-03
    """RSI 相对强弱指标

    Args:
        close: 收盘价
        periods: 周期列表

    Returns:
        DataFrame，列名为 RSI{period}
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    result = {}
    for p in periods:
        avg_gain = gain.ewm(alpha=1/p, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/p, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - 100 / (1 + rs)
        result[f"RSI{p}"] = rsi

    return pd.DataFrame(result)


def rsi_overbought(rsi: pd.Series, threshold: float = 70) -> pd.Series:
    """RSI 超买"""
    return (rsi > threshold).astype(int)


def rsi_oversold(rsi: pd.Series, threshold: float = 30) -> pd.Series:
    """RSI 超卖"""
    return (rsi < threshold).astype(int)
```

### 3.6.3 CCI

```python
def calc_cci(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """CCI 顺势指标

    Args:
        high, low, close: 高低收
        period: 周期

    Returns:
        Series: CCI 值
    """
    tp = (high + low + close) / 3
    ma = tp.rolling(period, min_periods=1).mean()
    md = tp.rolling(period, min_periods=1).apply(
        lambda x: np.mean(np.abs(x - x.mean())), raw=True
    )
    cci = (tp - ma) / (0.015 * md + 1e-9)
    return cci
```

## 3.7 通道类指标

### 3.7.1 布林带

```python
# indicators/channels.py
import pandas as pd

def calc_boll(close: pd.Series,
              period: int = 20,
              k: float = 2.0) -> pd.DataFrame:
    """布林带

    Args:
        close: 收盘价
        period: 周期
        k: 标准差倍数

    Returns:
        DataFrame with columns: [BOLL_MID, BOLL_UP, BOLL_DOWN, BOLL_WIDTH, BOLL_PB]
        - BOLL_MID: 中轨（MA）
        - BOLL_UP: 上轨
        - BOLL_DOWN: 下轨
        - BOLL_WIDTH: 带宽（(上-下)/中）
        - BOLL_PB: %b（价格在带中的位置，0=下轨，1=上轨）
    """
    mid = close.rolling(period, min_periods=1).mean()
    std = close.rolling(period, min_periods=1).std()

    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower) / (mid + 1e-9)
    percent_b = (close - lower) / (upper - lower + 1e-9)

    return pd.DataFrame({
        "BOLL_MID": mid,
        "BOLL_UP": upper,
        "BOLL_DOWN": lower,
        "BOLL_WIDTH": width,
        "BOLL_PB": percent_b
    })
```

### 3.7.2 ATR

```python
def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """ATR 真实波幅

    Args:
        high, low, close: 高低收
        period: 周期

    Returns:
        Series: ATR 值
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return wilder_smooth(tr, period)
```

### 3.7.3 Donchian Channel

```python
def calc_donchian(high: pd.Series, low: pd.Series,
                  period: int = 20) -> pd.DataFrame:
    """Donchian 通道

    Args:
        high, low: 最高最低价
        period: 周期

    Returns:
        DataFrame with columns: [DC_UP, DC_LOW, DC_MID]
    """
    upper = high.rolling(period, min_periods=1).max()
    lower = low.rolling(period, min_periods=1).min()
    mid = (upper + lower) / 2

    return pd.DataFrame({
        "DC_UP": upper,
        "DC_LOW": lower,
        "DC_MID": mid
    })
```

## 3.8 量价类指标

### 3.8.1 OBV

```python
# indicators/volume.py
import pandas as pd
import numpy as np

def calc_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """OBV 能量潮

    Args:
        close: 收盘价
        volume: 成交量

    Returns:
        Series: 累计 OBV
    """
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()
```

### 3.8.2 VWAP

```python
def calc_vwap(high: pd.Series, low: pd.Series, close: pd.Series,
              volume: pd.Series, period: int = 20) -> pd.Series:
    """VWAP 成交量加权均价（滚动 N 日）

    Returns:
        Series: VWAP
    """
    tp = (high + low + close) / 3
    vwap = (tp * volume).rolling(period, min_periods=1).sum() / \
           (volume.rolling(period, min_periods=1).sum() + 1e-9)
    return vwap
```

### 3.8.3 量比

```python
def calc_volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """量比

    Args:
        volume: 成交量
        period: 比较周期

    Returns:
        Series: 量比（今日成交量 / 过去 N 日均量）
    """
    return volume / volume.rolling(period, min_periods=1).mean()
```

### 3.8.4 MFI

```python
def calc_mfi(high: pd.Series, low: pd.Series, close: pd.Series,
             volume: pd.Series, period: int = 14) -> pd.Series:
    """MFI 资金流量指标

    Args:
        high, low, close, volume: 价格成交量
        period: 周期

    Returns:
        Series: MFI 值（0-100）
    """
    tp = (high + low + close) / 3
    rmf = tp * volume

    positive = pd.Series(0.0, index=close.index)
    negative = pd.Series(0.0, index=close.index)
    positive[tp > tp.shift(1)] = rmf[tp > tp.shift(1)]
    negative[tp < tp.shift(1)] = rmf[tp < tp.shift(1)]

    pmf = positive.rolling(period, min_periods=1).sum()
    nmf = negative.rolling(period, min_periods=1).sum()
    mfr = pmf / (nmf + 1e-9)
    mfi = 100 - 100 / (1 + mfr)
    return mfi
```

## 3.9 一键计算所有指标

```python
# indicators/pipeline.py
import pandas as pd
import numpy as np
from pathlib import Path


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一键计算所有 12 个技术指标

    注意：MA5/MA10/MA20/MA30/MA60/MA120/MA250 已从金玥数据中读取
    （列名 MA5, MA10, ..., MA250），其他指标需自己算

    Args:
        df: 含 OHLCV 的 DataFrame（来自金玥数据 + 列名标准化）

    Returns:
        原始 df + 所有指标列
    """
    result = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    # === 趋势类（MA 来自金玥数据，只算 MACD/DMI/排列）===
    if any(f"MA{n}" not in result.columns for n in [5, 10, 20, 60, 120, 250]):
        result = pd.concat([result, calc_ma(close)], axis=1)
    macd = calc_macd(close)
    result = pd.concat([result, macd], axis=1)
    # 修复 C13: DMI 内部已算 ATR（tr 序列），避免重复计算
    dmi = calc_dmi_adx(high, low, close)
    result = pd.concat([result, dmi], axis=1)
    # ATR 单独算一次（清晰、不依赖函数属性 hack，修复 B2 + C33）
    result["ATR"] = calc_atr(high, low, close)
    result["MA_ALIGN"] = calc_ma_alignment(close)
    result["MA_CONV"] = calc_ma_convergence(close)

    # === 动量类 ===
    kdj = calc_kdj(high, low, close)
    result = pd.concat([result, kdj], axis=1)
    rsi = calc_rsi(close)
    result = pd.concat([result, rsi], axis=1)
    result["CCI"] = calc_cci(high, low, close)

    # === 通道类 ===
    boll = calc_boll(close)
    result = pd.concat([result, boll], axis=1)
    dc = calc_donchian(high, low)
    result = pd.concat([result, dc], axis=1)

    # === 量价类 ===
    result["OBV"] = calc_obv(close, vol)
    result["OBV_MA"] = result["OBV"].rolling(20, min_periods=1).mean()
    result["VWAP"] = calc_vwap(high, low, close, vol)
    result["VOL_RATIO"] = calc_volume_ratio(vol)
    result["MFI"] = calc_mfi(high, low, close, vol)

    return result


def calc_indicators_with_cache(
    symbol: str,
    df: pd.DataFrame = None,
    cache_dir: str = "data/processed",
    data_dir: str = "data/data-by-stock",
    force_recalc: bool = False
) -> pd.DataFrame:
    """带缓存的一键计算（推荐）

    工作流程：
    1. 检查 data/processed/{symbol}.parquet 是否存在
    2. 如果存在且日期覆盖 → 加载缓存
    3. 如果不存在或日期不够 → 计算并缓存

    Args:
        symbol: 股票代码（如 "000001"）
        df: 原始数据（None 则自动从 data-by-stock 加载）
        cache_dir: 缓存目录
        data_dir: 原始数据目录
        force_recalc: 强制重算

    Returns:
        含所有指标的 DataFrame
    """
    cache_path = Path(cache_dir) / f"{symbol}.parquet"

    # 检查缓存
    if not force_recalc and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        if "date" in cached.columns:
            cached_max = cached["date"].max()

            # 如果有 df 输入，检查是否覆盖
            if df is not None and "date" in df.columns:
                df_max = df["date"].max()
                if cached_max >= df_max:
                    return cached

    # 加载数据
    if df is None:
        from data.loader import load_stock_series
        df = load_stock_series(symbol, data_dir=data_dir)

    # 计算
    result = calc_all_indicators(df)

    # 缓存
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, compression="snappy")
    return result


def batch_calc_indicators(
    symbols: list[str],
    cache_dir: str = "data/processed",
    data_dir: str = "data/data-by-stock",
    n_workers: int = 4
) -> dict[str, pd.DataFrame]:
    """批量计算多只股票的指标

    Args:
        symbols: 股票代码列表
        cache_dir: 缓存目录
        data_dir: 原始数据目录
        n_workers: 并发数

    Returns:
        {symbol: DataFrame} 字典
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    results = {}
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(calc_indicators_with_cache, sym, None, cache_dir, data_dir): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results[sym] = future.result()
            except Exception as e:
                print(f"Failed for {sym}: {e}")

    return results
```

## 3.10 与 02-data-layer 的衔接

```python
# scripts/precompute_indicators.py
"""预计算所有股票的技术指标（首次运行 + 每月更新）"""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from data.storage import ParquetStorage
from indicators.pipeline import batch_calc_indicators


def main():
    """预计算所有股票指标"""
    # 1. 获取所有股票
    storage = ParquetStorage("data/data-by-stock")
    symbols = storage.list_symbols("stock")
    print(f"Total symbols: {len(symbols)}")

    # 2. 批量计算（首次可能需要 30 分钟）
    results = batch_calc_indicators(
        symbols,
        cache_dir="data/processed",
        data_dir="data/data-by-stock",
        n_workers=4
    )

    print(f"Computed: {len(results)} symbols")
    print(f"Cache dir: data/processed/")

    # 3. 统计
    success = sum(1 for v in results.values() if not v.empty)
    print(f"Success rate: {success}/{len(symbols)}")


if __name__ == "__main__":
    main()
```

## 3.11 性能基准

| 指标数 | 数据量 | 计算时间（单标的） |
|---|---|---|
| 12 | 10 年日 K（2400 行） | ~50ms |
| 12 | 全 A 5841 只 | ~5 分钟（首次） |
| 12 + 缓存 | 全 A 5841 只 | ~10 秒（命中后） |

优化手段：
- 向量化（避免 for 循环）
- 缓存到 `data/processed/`
- 并行（ProcessPoolExecutor）

## 3.12 单元测试

```python
# tests/test_indicators.py
import pytest
import pandas as pd
import numpy as np
from indicators.trend import calc_ma, calc_macd, calc_dmi_adx
from indicators.momentum import calc_kdj, calc_rsi
from indicators.channels import calc_boll, calc_atr
from indicators.volume import calc_obv
from indicators.pipeline import calc_all_indicators


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 100
    close = pd.Series(np.cumsum(np.random.randn(n)) + 100)
    high = close + np.abs(np.random.randn(n))
    low = close - np.abs(np.random.randn(n))
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(np.random.randint(1000000, 10000000, n))
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume
    })


def test_calc_ma(sample_df):
    """MA 计算正确性"""
    ma = calc_ma(sample_df["close"], periods=[5, 20])
    assert "MA5" in ma.columns
    assert "MA20" in ma.columns
    assert len(ma) == len(sample_df)


def test_calc_macd(sample_df):
    """MACD 计算正确性"""
    macd = calc_macd(sample_df["close"])
    assert all(c in macd.columns for c in ["DIF", "DEA", "MACD"])
    assert np.allclose(macd["MACD"], 2 * (macd["DIF"] - macd["DEA"]))


def test_calc_kdj_range(sample_df):
    """KDJ 值应在合理范围"""
    kdj = calc_kdj(sample_df["high"], sample_df["low"], sample_df["close"])
    assert kdj["K"].between(0, 100).all()
    assert kdj["D"].between(0, 100).all()


def test_calc_rsi_range(sample_df):
    """RSI 应在 [0, 100]"""
    rsi = calc_rsi(sample_df["close"])
    for col in rsi.columns:
        assert rsi[col].between(0, 100).all()


def test_calc_boll(sample_df):
    """布林带：上轨 > 中轨 > 下轨"""
    boll = calc_boll(sample_df["close"])
    assert (boll["BOLL_UP"] >= boll["BOLL_MID"]).all()
    assert (boll["BOLL_MID"] >= boll["BOLL_DOWN"]).all()


def test_calc_atr_positive(sample_df):
    """ATR 始终为正"""
    atr = calc_atr(sample_df["high"], sample_df["low"], sample_df["close"])
    assert (atr >= 0).all()


def test_pipeline_integration(sample_df):
    """一键计算所有指标"""
    result = calc_all_indicators(sample_df)
    # 应包含所有指标列
    expected = ["DIF", "DEA", "MACD", "K", "D", "J", "RSI6", "BOLL_MID",
                "ATR", "DC_UP", "OBV", "MFI"]
    for col in expected:
        assert col in result.columns
```

## 3.13 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 指标全为 NaN | 数据不足（少于 period） | `min_periods=1` |
| MACD 早于 26 日为空 | EMA 需要 warmup | ewm(min_periods=1) |
| 布林带为常数 | 数据无波动 | 检查数据质量 |
| ADX 永远 < 20 | 横盘市 | 正常，但需注意 |
| 缓存文件不更新 | 数据已更新但缓存未失效 | 删除缓存或用 `force_recalc=True` |

## 3.14 依赖

```txt
# requirements.txt
pandas>=1.5.0
numpy>=1.20.0
pyarrow>=10.0.0
# 可选：ta-lib（更快但需要 C 库）
# ta-lib>=0.4.0
```

## 3.15 ATOS 适配说明

| ATOS 需要的指标 | 状态 | 来源 |
|---|---|---|
| MA20/MA60/MA120/MA250 | ✅ 直接用 | 金玥数据自带 |
| MACD (12,26,9) | ⚠️ 自己算 | calc_macd() |
| KDJ (9,3,3) | ⚠️ 自己算 | calc_kdj() |
| RSI (6,12,24) | ⚠️ 自己算 | calc_rsi() |
| BOLL (20,2) | ⚠️ 自己算 | calc_boll() |
| ATR (14) | ⚠️ 自己算 | calc_atr() |
| DMI/ADX (14) | ⚠️ 自己算 | calc_dmi_adx() |
| Donchian (20) | ⚠️ 自己算 | calc_donchian() |
| OBV | ⚠️ 自己算 | calc_obv() |
| MFI (14) | ⚠️ 自己算 | calc_mfi() |
| 量比 | ✅ 直接用 | 金玥数据 vol_ratio |
| VWAP | ⚠️ 自己算 | calc_vwap() |
| 涨跌幅 (3/6/10/25日) | ✅ 直接用 | 金玥数据 |

**结论**：12 个核心指标中，3 个直接用金玥数据，9 个自己算。**完全可行**。
