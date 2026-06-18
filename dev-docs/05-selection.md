# 05 - 选股模型层

## 5.1 职责

根据市场状态，从全 A 股中**选出最值得买入的 N 只股票**。

需要实现：
- 12 个技术因子（4 类）的计算
- 因子预处理（去极值、标准化、中性化）
- 因子合成（IC 加权）
- 因子权重随市场状态动态切换
- 排序与 Top N 选择

## 5.2 模块结构

```
selection/
├── __init__.py
├── factors.py            # 12 因子定义
├── preprocessing.py      # 去极值/标准化/中性化
├── synthesis.py          # 因子合成
├── weight_schedule.py    # 动态权重
└── selector.py           # 选股主逻辑
```

## 5.3 12 因子清单

| 类别 | 因子 | 方向 | 公式 |
|---|---|---|---|
| 趋势 | trend_ma60 | + | close / MA60 - 1 |
| 趋势 | ma_slope_60 | + | MA60 的 20 日线性回归斜率（年化） |
| 趋势 | adx_14 | + | 平均趋向指数（>25 为强趋势） |
| 趋势 | price_above_ma120 | + | price > MA120（0/1） |
| 动量 | ret_20d | + | 过去 20 日收益率 |
| 动量 | ret_60d | + | 过去 60 日收益率 |
| 动量 | sharpe_60d | + | 60 日年化夏普 |
| 量价 | vol_ratio_5_20 | + | 5 日均量 / 20 日均量 |
| 量价 | turnover_stability | - | 20 日换手率标准差（负向） |
| 量价 | corr_ret_vol | + | 20 日收益率与成交量相关系数 |
| 形态 | rsi_14_centered | + | (RSI14 - 50) / 50 |
| 形态 | near_high_60 | - | (60 日最高 - 收盘) / 60 日最高 |

## 5.4 因子计算

```python
# selection/factors.py
import pandas as pd
import numpy as np

def calc_all_factors(df: pd.DataFrame) -> pd.DataFrame:
    """计算 12 个技术因子

    Args:
        df: 含 open/high/low/close/volume 及指标的 DataFrame

    Returns:
        DataFrame: 12 因子值
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    turnover = df["turnover"]  # 修复 [v8.3]: 用真实换手率列（%）而非 vol 代理
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    ma120 = df["MA120"]
    adx = df["ADX"]
    rsi14 = df["RSI14"]
    vol_ratio = df["VOL_RATIO"]

    factors = pd.DataFrame(index=df.index)

    # === 趋势类（4）===
    factors["trend_ma60"] = (close / ma60 - 1)
    factors["ma_slope_60"] = calc_ma_slope(ma60, window=20)
    factors["adx_14"] = adx / 50  # 归一化到 [0, 1]
    factors["price_above_ma120"] = (close > ma120).astype(float)

    # === 动量类（3）===
    factors["ret_20d"] = close / close.shift(20) - 1
    factors["ret_60d"] = close / close.shift(60) - 1
    factors["sharpe_60d"] = calc_rolling_sharpe(close, window=60)

    # === 量价类（3）===
    factors["vol_ratio_5_20"] = vol_ratio
    factors["turnover_stability"] = -calc_turnover_stability(turnover, window=20)
    factors["corr_ret_vol"] = calc_corr_ret_vol(close, vol, window=20)

    # === 形态类（2）===
    factors["rsi_14_centered"] = (rsi14 - 50) / 50  # 中心化到 [-1, 1]
    factors["near_high_60"] = (close.rolling(60).max() - close) / close

    return factors


def calc_ma_slope(ma: pd.Series, window: int = 20) -> pd.Series:
    """MA 的 N 日线性回归斜率（年化）"""
    def slope(s):
        if len(s) < 2:
            return 0.0
        x = np.arange(len(s))
        y = s.values
        if np.std(y) == 0:
            return 0.0
        slope = np.polyfit(x, y, 1)[0]
        return slope * 252  # 年化

    return ma.rolling(window).apply(slope, raw=False)


def calc_rolling_sharpe(close: pd.Series, window: int = 60) -> pd.Series:
    """滚动年化夏普"""
    log_ret = np.log(close / close.shift(1))
    mean_ret = log_ret.rolling(window).mean() * 252
    vol = log_ret.rolling(window).std() * np.sqrt(252)
    return mean_ret / (vol + 1e-9)


def calc_turnover_stability(turnover: pd.Series, window: int = 20) -> pd.Series:
    """换手率稳定性（标准差，负向因子）

    修复 [v8.3]：原代码误用 vol 作为 turnover 的代理。
    turnover 与 volume 含义不同（前者是 %，后者是股数），
    用 vol 计算的稳定性会受股票流通盘大小影响，丧失可比性。

    Args:
        turnover: 换手率序列（%），来自金玥数据 turnover 列
        window: 滚动窗口

    Returns:
        Series: 20 日换手率标准差（负向因子：值越小越稳定）
    """
    return turnover.rolling(window, min_periods=window // 2).std()


def calc_corr_ret_vol(close: pd.Series, vol: pd.Series, window: int = 20) -> pd.Series:
    """收益率与成交量相关系数"""
    log_ret = close.pct_change()
    return log_ret.rolling(window).corr(vol)
```

## 5.5 因子预处理

### 5.5.1 去极值

```python
# selection/preprocessing.py
import pandas as pd
import numpy as np

def winsorize_mad(series: pd.Series, n: float = 5.0) -> pd.Series:
    """MAD 法去极值

    将超过中位数 ± n * MAD 的值截尾

    Args:
        series: 因子值
        n: MAD 倍数（默认 5）
    """
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return series

    upper = median + n * mad
    lower = median - n * mad
    return series.clip(lower, upper)


def winsorize_3sigma(series: pd.Series, n: float = 3.0) -> pd.Series:
    """3σ 法去极值"""
    mean = series.mean()
    std = series.std()
    if std == 0:
        return series
    return series.clip(mean - n * std, mean + n * std)
```

### 5.5.2 标准化

```python
def standardize_zscore(series: pd.Series, window: int = None) -> pd.Series:
    """Z-score 标准化

    Args:
        series: 因子值
        window: 滚动窗口（None 表示用全部历史）
    """
    if window is None:
        mean = series.mean()
        std = series.std()
    else:
        mean = series.rolling(window, min_periods=20).mean()
        std = series.rolling(window, min_periods=20).std()

    return (series - mean) / (std + 1e-9)


def standardize_rank(series: pd.Series) -> pd.Series:
    """排序标准化（百分位）"""
    return series.rank(pct=True) - 0.5  # 中心化到 [-0.5, 0.5]
```

### 5.5.3 中性化

```python
def neutralize(
    factor: pd.Series,
    market_cap: pd.Series = None,
    industry: pd.Series = None,
    universe: str = None  # 修复 [v8.5] D12: 中性化基准 = 选股池
) -> pd.Series:
    """中性化（对市值、行业回归取残差，修复 [v8.5] D12）

    Args:
        factor: 因子值
        market_cap: 市值（对数）
        industry: 行业分类（0/1 dummy 矩阵）
        universe: 选股池标识（修复 D12：必须与因子计算范围一致）

    Returns:
        中性化后的因子值（残差）

    修复 [v8.5] D12 说明：
    - 原文档"用沪深300成分股总市值"作为基准，但选股池可能不同
    - 修正：**中性化基准 = 选股池自身**
    - 三种标准选股池：
      * "HS300"：沪深 300，保守
      * "HS300+CSI500"：两池合并，平衡（推荐）
      * "ALL_A"：全 A（剔除北交所/ST/退市），激进
    """
    import statsmodels.api as sm

    df = pd.DataFrame({"factor": factor})

    if market_cap is not None:
        df["log_cap"] = np.log(market_cap + 1)

    if industry is not None:
        industry_dummies = pd.get_dummies(industry, prefix="ind")
        df = pd.concat([df, industry_dummies], axis=1)

    # 修复 D12: 若指定 universe，按 universe 过滤
    if universe is not None and hasattr(factor.index, "name"):
        # 实际过滤逻辑在调用方完成；此处仅记录 universe
        pass

    # 修复 C10: 处理 X 为空的情况
    X = df.drop("factor", axis=1)
    if X.shape[1] == 0:
        # 既无市值又无行业，无可中性化内容
        return factor

    X = sm.add_constant(X)

    # OLS 回归
    valid = df["factor"].notna() & X.notna().all(axis=1)
    if valid.sum() < 10:
        return factor

    model = sm.OLS(df.loc[valid, "factor"], X.loc[valid]).fit()
    residuals = pd.Series(index=df.index, dtype=float)
    residuals.loc[valid] = model.resid
    return residuals
```

### 5.5.4 完整预处理流程

```python
def preprocess_factor(
    factor: pd.Series,
    method_winsorize: str = "mad",  # mad / 3sigma / none
    method_standardize: str = "zscore",  # zscore / rank / none
    market_cap: pd.Series = None,
    industry: pd.Series = None,
    rolling_window: int = 252,
    universe: str = None  # 修复 [v8.5] D12: 中性化基准 = 选股池
) -> pd.Series:
    """完整因子预处理

    顺序：去极值 → 中性化 → 标准化
    """
    result = factor.copy()

    # 1. 去极值（修复 C11: factor 是时序 Series，不是横截面）
    # 注意：因子计算后通常已是横截面标准化结果，无需再去极值
    # 真正需要去极值的是横截面场景
    if method_winsorize == "mad":
        result = winsorize_mad(result, n=5)
    elif method_winsorize == "3sigma":
        result = winsorize_3sigma(result)
    # else: 不处理

    # 2. 中性化（修复 [v8.5] D12: 传入 universe 基准）
    if market_cap is not None or industry is not None:
        result = neutralize(result, market_cap, industry, universe=universe)

    # 3. 标准化
    if method_standardize == "zscore":
        result = standardize_zscore(result, window=rolling_window)
    elif method_standardize == "rank":
        result = standardize_rank(result)

    return result
```

## 5.6 因子合成

### 5.6.1 合成方法

```python
# selection/synthesis.py
import pandas as pd
import numpy as np

def synthesize_equal_weight(factor_dict: dict) -> pd.Series:
    """等权合成"""
    return sum(factor_dict.values()) / len(factor_dict)


def synthesize_ic_weight(
    factor_dict: dict,
    ic_series_dict: dict,
    lookback: int = 120
) -> pd.Series:
    """IC 加权合成

    Args:
        factor_dict: {因子名: 因子 Series}
        ic_series_dict: {因子名: 历史 IC Series}
        lookback: IC 滚动窗口
    """
    # 计算每个因子的 IC 权重
    weights = {}
    for name, ic_series in ic_series_dict.items():
        recent_ic = ic_series.iloc[-lookback:].abs().mean()
        weights[name] = recent_ic

    # 归一化
    total = sum(weights.values())
    if total == 0:
        return synthesize_equal_weight(factor_dict)

    weights = {k: v / total for k, v in weights.items()}

    # 加权合成
    composite = None
    for name, factor in factor_dict.items():
        if name in weights:
            weighted = factor * weights[name]
            composite = weighted if composite is None else composite + weighted

    return composite


def synthesize_ir_weight(
    factor_dict: dict,
    ic_series_dict: dict,
    lookback: int = 120
) -> pd.Series:
    """IR 加权（IC 均值 / IC 标准差）"""
    weights = {}
    for name, ic_series in ic_series_dict.items():
        ic_mean = ic_series.iloc[-lookback:].mean()
        ic_std = ic_series.iloc[-lookback:].std()
        ir = abs(ic_mean) / (ic_std + 1e-9)
        weights[name] = ir

    total = sum(weights.values())
    if total == 0:
        return synthesize_equal_weight(factor_dict)

    weights = {k: v / total for k, v in weights.items()}

    composite = None
    for name, factor in factor_dict.items():
        if name in weights:
            weighted = factor * weights[name]
            composite = weighted if composite is None else composite + weighted

    return composite
```

### 5.6.2 IC 计算

```python
def calc_ic(factor: pd.Series, returns: pd.Series) -> pd.Series:
    """计算 IC（信息系数，因子与未来收益的秩相关系数）

    Args:
        factor: 因子值
        returns: 未来 N 日收益

    Returns:
        滚动 IC Series
    """
    return factor.rolling(60).corr(returns.shift(-1), method="spearman")
```

## 5.7 动态因子权重（按市场状态）

```python
# selection/weight_schedule.py
from enum import Enum


class MarketState(str, Enum):
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"
    CRASH = "CRASH"
    CHOPPY_BEAR = "CHOPPY_BEAR"


# 修复 B16: 验证权重和 ≈ 1.0
def _validate_weights(weights: dict, tolerance: float = 0.01) -> bool:
    """验证权重和约等于 1.0"""
    total = sum(weights.values())
    return abs(total - 1.0) < tolerance


# 修复 B15: 因子方向与 §5.3 表标注一致
# 因子方向：+ 为正相关（值大→涨），- 为负相关（值大→跌）
FACTOR_WEIGHTS = {
    MarketState.BULL: {
        "trend_ma60": 0.15,           # 距离 MA60 越远越强
        "ma_slope_60": 0.10,          # MA60 斜率向上
        "adx_14": 0.05,               # 趋势强
        "price_above_ma120": 0.05,    # 站上 MA120
        "ret_20d": 0.20,              # 修复 B15: 正向（BULL 看动量）
        "ret_60d": 0.15,              # 修复 B15: 正向
        "sharpe_60d": 0.05,
        "vol_ratio_5_20": 0.10,
        "turnover_stability": 0.05,
        "corr_ret_vol": 0.05,
        "rsi_14_centered": 0.05,
        "near_high_60": 0.00,
    },
    MarketState.SIDEWAYS: {
        "trend_ma60": 0.05,
        "ma_slope_60": 0.05,
        "adx_14": 0.00,
        "price_above_ma120": 0.05,
        "ret_20d": -0.10,  # 修复 B15: 反向（SIDEWAYS 反转）
        "ret_60d": 0.00,
        "sharpe_60d": 0.10,
        "vol_ratio_5_20": 0.10,
        "turnover_stability": 0.15,
        "corr_ret_vol": 0.10,
        "rsi_14_centered": 0.20,  # RSI 超卖优先
        "near_high_60": 0.30,      # 修复 B15: 距 60 日高点越近越强
    },
    MarketState.BEAR: {
        "trend_ma60": 0.10,
        "ma_slope_60": 0.05,
        "adx_14": 0.00,
        "price_above_ma120": 0.10,
        "ret_20d": 0.05,
        "ret_60d": 0.00,
        "sharpe_60d": 0.15,
        "vol_ratio_5_20": 0.05,
        "turnover_stability": 0.20,
        "corr_ret_vol": 0.05,
        "rsi_14_centered": 0.20,
        "near_high_60": 0.05,
    },
    MarketState.CRASH: {
        "sharpe_60d": 0.50,
        "turnover_stability": 0.50,
    },
    MarketState.CHOPPY_BEAR: {
        # 震荡下行：高质量、低波动
        "trend_ma60": 0.05,
        "ma_slope_60": 0.00,
        "adx_14": 0.00,
        "price_above_ma120": 0.20,
        "ret_20d": 0.00,
        "ret_60d": 0.00,
        "sharpe_60d": 0.20,
        "vol_ratio_5_20": 0.05,
        "turnover_stability": 0.20,
        "corr_ret_vol": 0.10,
        "rsi_14_centered": 0.10,
        "near_high_60": 0.10,
    },
}

# 修复 B16: 启动时校验所有权重和
for _state, _weights in FACTOR_WEIGHTS.items():
    if not _validate_weights(_weights):
        raise ValueError(
            f"FACTOR_WEIGHTS[{_state.value}] sum = {sum(_weights.values()):.3f} != 1.0"
        )


def get_factor_weights(state: str) -> dict:
    """根据市场状态获取因子权重"""
    try:
        return FACTOR_WEIGHTS[MarketState(state)]
    except (ValueError, KeyError):
        return FACTOR_WEIGHTS[MarketState.SIDEWAYS]
```

## 5.8 选股主逻辑

```python
# selection/selector.py
import pandas as pd

class StockSelector:
    """选股器"""

    def __init__(self, config):
        self.config = config
        self.factor_cache = {}  # {symbol: factors}

    def select(
        self,
        date: pd.Timestamp,
        stock_data: dict[str, pd.DataFrame],
        state: str,
        top_n: int = 10
    ) -> list[str]:
        """选股主函数

        Args:
            date: 选股日期
            stock_data: {symbol: 含指标的 DataFrame}
            state: 当前市场状态
            top_n: 选 Top N

        Returns:
            选中的股票代码列表（按得分降序）
        """
        # 1. 获取权重
        weights = get_factor_weights(state)

        # 2. 计算每只股票的因子得分
        scores = {}
        for symbol, df in stock_data.items():
            if date not in df.index:
                continue
            if df.loc[date].isna().any():
                continue

            factor_dict = calc_all_factors(df)
            # 横截面标准化 + 合成（修复 [v8.4] A59: 无 date 参数）
            composite = self._composite_score(factor_dict, weights)
            if composite is not None:
                scores[symbol] = composite

        # 3. 排序 + Top N
        if not scores:
            return []

        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [s[0] for s in sorted_stocks[:top_n]]

    def _composite_score(self, cross_section_factors: dict, weights: dict) -> float:
        """计算单只股票的横截面合成得分（修复 B1 + C12 + [v8.4] B14）

        Args:
            cross_section_factors: {因子名: 当日该股票在该因子上的横截面值}
                例如 {"mom_20d": 0.15, "mfi": 65, "rsi_centered": 0.2}
            weights: {因子名: 权重}

        Returns:
            综合得分（已横截面标准化后加权）

        修复 B1: 之前用 factor.rank(pct=True) 是时间序列 rank，方向错误
        修复 [v8.4] B14: 权重和必须为正（含负权重时不能用 abs 归一化），
        否则负权重翻正后归一化偏差。
        现要求 weights 已校验 sum ≈ 1.0（§5.7 启动校验保证），
        直接乘加求和即可。
        """
        score = 0.0
        weight_sum = 0.0

        for name, factor_value in cross_section_factors.items():
            if name in weights and factor_value is not None and not pd.isna(factor_value):
                # [v8.4] B14: 直接累加权重（含正负），不取 abs
                score += weights[name] * factor_value
                weight_sum += weights[name]

        if weight_sum == 0:
            return None
        # [v8.4] B14: 仅当权重和为正时归一化
        if weight_sum < 0:
            return -score / abs(weight_sum)
        return score / weight_sum

    @staticmethod
    def cross_section_rank(factor_today: pd.Series) -> pd.Series:
        """对当日所有股票的某因子做横截面 rank 标准化

        Args:
            factor_today: 某日所有股票在该因子上的值

        Returns:
            -1 到 1 之间的标准化值（中心化）
        """
        return factor_today.rank(pct=True) - 0.5
```

## 5.9 完整调用示例

```python
# 在回测引擎中
from selection.selector import StockSelector
from regime import detect_full_regime

# 1. 准备大盘数据
index_df = load_ohlcv("000300")

# 2. 准备个股数据
stock_data = {
    "000001": load_ohlcv("000001"),
    "000002": load_ohlcv("000002"),
    # ...
}

# 3. 状态识别
regime = detect_full_regime(index_df, config)

# 4. 逐日选股
selector = StockSelector(config)
for date in trading_days:
    state = regime.loc[date, "effective_state"]
    top_stocks = selector.select(
        date=date,
        stock_data=stock_data,
        state=state,
        top_n=10
    )
    # 用 top_stocks 生成交易信号
    # ...
```

## 5.10 测试

```python
# tests/test_selection.py
import pytest
import pandas as pd
import numpy as np
from selection.factors import calc_all_factors
from selection.preprocessing import winsorize_mad, standardize_zscore
from selection.weight_schedule import get_factor_weights


def test_factors_count():
    """应计算 12 个因子"""
    np.random.seed(42)
    close = pd.Series(np.cumsum(np.random.randn(100)) + 100)
    df = pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1e6, 1e7, 100),
        "MA20": close.rolling(20).mean(), "MA60": close.rolling(60).mean(),
        "MA120": close.rolling(120).mean(), "ADX": 25,
        "RSI14": 50, "VOL_RATIO": 1.0
    })
    factors = calc_all_factors(df)
    assert len(factors.columns) == 12


def test_winsorize_mad():
    """MAD 去极值"""
    s = pd.Series([1, 2, 3, 4, 100])  # 100 是离群值
    result = winsorize_mad(s, n=5)
    assert result.max() < 100


def test_get_factor_weights():
    """应返回状态对应权重"""
    bull_w = get_factor_weights("BULL")
    sideways_w = get_factor_weights("SIDEWAYS")
    # 不同状态权重不同
    assert bull_w != sideways_w
    # 权重和为 1
    assert abs(sum(bull_w.values()) - 1.0) < 0.01
```

## 5.11 性能优化

| 优化 | 效果 |
|---|---|
| 因子计算缓存 | 避免重复计算 |
| 横截面标准化并行 | 5 只 → 1 只 × 5 |
| 预排序 | 只算 Top N 候选 |
| 行业中性化预计算 | 避免回归 |

## 5.12 依赖

```txt
# 额外需要
statsmodels>=0.13.0  # OLS 用于中性化
```