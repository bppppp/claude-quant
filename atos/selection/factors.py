"""12 因子计算"""
import numpy as np
import pandas as pd


def calc_ma_slope(ma: pd.Series, window: int = 20) -> pd.Series:
    """MA 的 N 日线性回归斜率（年化）- 向量化实现

    公式: slope = (N*sum(xy) - sum(x)*sum(y)) / (N*sum(x²) - sum(x)²)
    对于 x = 0, 1, ..., N-1, sum(x) = N(N-1)/2, sum(x²) = N(N-1)(2N-1)/6
    简化为：slope = (12 * sum((i - i_mean) * (y - y_mean))) / (N * (N²-1))
    """
    n = window
    i_arr = np.arange(n, dtype=np.float64)
    i_mean = (n - 1) / 2.0
    # 预先计算权重 (i - i_mean)
    w = (i_arr - i_mean)

    # rolling 计算 (y - y_mean) - 用 cumsum 高效
    # 对每个窗口：sum((i - i_mean) * (y - y_mean)) = sum(w * y_centered)
    # 等价于：sum(w * y) - mean(y) * sum(w) = sum(w * y)（因为 sum(w) = 0）

    # 方法：把 y 看成数组，用滑动窗口点积
    y = ma.values
    if len(y) < n:
        return pd.Series(0.0, index=ma.index)

    # 构建 w 矩阵 (n 个点)，滑动窗口内 w @ y_window
    # 用 cumsum trick 加速
    # 实际上 pandas rolling.dot 不存在，用 strided 内存视图 + np.dot
    from numpy.lib.stride_tricks import sliding_window_view
    y_windows = sliding_window_view(y, n)  # (T-N+1, N)
    # 滑动加权和 = y_windows @ w / n  (中心化后 y 与 (i-i_mean) 的协方差 * N)
    cov_sum = y_windows @ w  # (T-N+1,)

    # cov = cov_sum / N, slope = cov * 12 / (N * (N²-1))，年化 = slope * 252
    N = n
    slope = cov_sum * 12.0 / (N * (N * N - 1)) * 252

    # 对齐索引（前 N-1 个为 NaN）
    out = pd.Series(np.nan, index=ma.index)
    out.iloc[n - 1:] = slope
    return out


def calc_rolling_sharpe(close: pd.Series, window: int = 60) -> pd.Series:
    """滚动年化夏普"""
    log_ret = np.log(close / close.shift(1))
    mean_ret = log_ret.rolling(window).mean() * 252
    vol = log_ret.rolling(window).std() * np.sqrt(252)
    return mean_ret / (vol + 1e-9)


def calc_turnover_stability(turnover: pd.Series, window: int = 20) -> pd.Series:
    """换手率稳定性（标准差，负向因子）"""
    return turnover.rolling(window, min_periods=max(1, window // 2)).std()


def calc_corr_ret_vol(close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    """收益率与成交量相关系数"""
    log_ret = close.pct_change()
    return log_ret.rolling(window).corr(volume)


def calc_all_factors(df: pd.DataFrame) -> pd.DataFrame:
    """计算 12 个技术因子

    输入：含 OHLCV + 指标的 DataFrame
    输出：12 因子
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    ma20 = df["MA20"]
    ma60 = df["MA60"]
    ma120 = df["MA120"]
    adx = df["ADX"]
    rsi14 = df["RSI14"]
    # 金玥数据 '换手率' 已是 percent
    if "turnover" in df.columns:
        turnover = df["turnover"]
    elif "换手率" in df.columns:
        turnover = df["换手率"]
    else:
        turnover = pd.Series(1.0, index=df.index)

    factors = pd.DataFrame(index=df.index)

    # 趋势类（4）
    factors["trend_ma60"] = (close / ma60 - 1)
    factors["ma_slope_60"] = calc_ma_slope(ma60, window=20)
    factors["adx_14"] = adx / 50  # 归一化到 [0, 1]（ADX 实际常 < 50）
    factors["price_above_ma120"] = (close > ma120).astype(float)

    # 动量类（3）
    factors["ret_20d"] = close / close.shift(20) - 1
    factors["ret_60d"] = close / close.shift(60) - 1
    factors["sharpe_60d"] = calc_rolling_sharpe(close, window=60)

    # 量价类（3）
    if "VOL_RATIO" in df.columns:
        factors["vol_ratio_5_20"] = df["VOL_RATIO"]
    else:
        factors["vol_ratio_5_20"] = 1.0
    factors["turnover_stability"] = -calc_turnover_stability(turnover, window=20)
    factors["corr_ret_vol"] = calc_corr_ret_vol(close, vol, window=20)

    # 形态类（3）
    factors["rsi_14_centered"] = (rsi14 - 50) / 50
    factors["near_high_60"] = (close.rolling(60).max() - close) / (close + 1e-9)
    # ATOS2 v2：补全 spec §7.1 第 13 因子 bb_width
    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        factors["bb_width"] = (df["BB_UPPER"] - df["BB_LOWER"]) / (ma20 + 1e-9)
    else:
        factors["bb_width"] = 0.0

    # ATOS2 v1 新增（1：price_momentum_5d）
    factors["price_momentum_5d"] = close / close.shift(5) - 1

    return factors
