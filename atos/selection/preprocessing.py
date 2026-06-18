"""因子预处理：去极值、标准化、中性化"""
import numpy as np
import pandas as pd


def winsorize_mad(series: pd.Series, n: float = 5.0) -> pd.Series:
    """MAD 法去极值"""
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


def standardize_zscore(series: pd.Series, window=None) -> pd.Series:
    """Z-score 标准化"""
    if window is None:
        mean = series.mean()
        std = series.std()
    else:
        mean = series.rolling(window, min_periods=20).mean()
        std = series.rolling(window, min_periods=20).std()
    return (series - mean) / (std + 1e-9)


def standardize_rank(series: pd.Series) -> pd.Series:
    """排序标准化（百分位中心化）"""
    return series.rank(pct=True) - 0.5


def neutralize(factor: pd.Series,
               market_cap: pd.Series = None,
               industry: pd.Series = None) -> pd.Series:
    """中性化（对市值、行业回归取残差）"""
    try:
        import statsmodels.api as sm
    except ImportError:
        return factor

    df = pd.DataFrame({"factor": factor})
    if market_cap is not None:
        df["log_cap"] = np.log(market_cap + 1)
    if industry is not None:
        industry_dummies = pd.get_dummies(industry, prefix="ind")
        df = pd.concat([df, industry_dummies], axis=1)

    X = df.drop("factor", axis=1)
    if X.shape[1] == 0:
        return factor

    X = sm.add_constant(X)

    valid = df["factor"].notna() & X.notna().all(axis=1)
    if valid.sum() < 10:
        return factor

    model = sm.OLS(df.loc[valid, "factor"], X.loc[valid]).fit()
    residuals = pd.Series(index=df.index, dtype=float)
    residuals.loc[valid] = model.resid
    return residuals


def preprocess_factor(factor: pd.Series,
                       method_winsorize: str = "mad",
                       method_standardize: str = "rank",
                       market_cap: pd.Series = None,
                       industry: pd.Series = None) -> pd.Series:
    """完整因子预处理

    顺序：去极值 -> 中性化 -> 标准化
    """
    result = factor.copy()

    if method_winsorize == "mad":
        result = winsorize_mad(result, n=5)
    elif method_winsorize == "3sigma":
        result = winsorize_3sigma(result)

    if market_cap is not None or industry is not None:
        result = neutralize(result, market_cap, industry)

    if method_standardize == "zscore":
        result = standardize_zscore(result)
    elif method_standardize == "rank":
        result = standardize_rank(result)

    return result
