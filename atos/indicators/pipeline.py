"""指标 pipeline - 一键计算所有指标"""
from pathlib import Path
import pandas as pd

from .trend import calc_ma, calc_macd, calc_dmi_adx, calc_ma_alignment, calc_ma_convergence
from .momentum import calc_kdj, calc_rsi, calc_cci
from .channels import calc_boll, calc_atr, calc_donchian
from .volume import calc_obv, calc_vwap, calc_volume_ratio, calc_mfi


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一键计算所有技术指标"""
    result = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    # 趋势类 - MA 从金玥数据读取，缺失则补算
    missing_ma = [n for n in [5, 10, 20, 30, 60, 120, 250] if f"MA{n}" not in result.columns]
    if missing_ma:
        ma_df = calc_ma(close, periods=tuple(missing_ma))
        result = pd.concat([result, ma_df], axis=1)

    macd = calc_macd(close)
    result = pd.concat([result, macd], axis=1)
    dmi = calc_dmi_adx(high, low, close)
    result = pd.concat([result, dmi], axis=1)
    result["ATR"] = calc_atr(high, low, close)
    result["MA_ALIGN"] = calc_ma_alignment(close)
    result["MA_CONV"] = calc_ma_convergence(close)

    # 动量类
    kdj = calc_kdj(high, low, close)
    result = pd.concat([result, kdj], axis=1)
    rsi = calc_rsi(close)
    result = pd.concat([result, rsi], axis=1)
    result["CCI"] = calc_cci(high, low, close)

    # 通道类
    boll = calc_boll(close)
    result = pd.concat([result, boll], axis=1)
    dc = calc_donchian(high, low)
    result = pd.concat([result, dc], axis=1)

    # 量价类
    result["OBV"] = calc_obv(close, vol)
    result["OBV_MA"] = result["OBV"].rolling(20, min_periods=1).mean()
    result["VWAP"] = calc_vwap(high, low, close, vol)
    if "vol_ratio" in df.columns:
        result["VOL_RATIO"] = df["vol_ratio"].fillna(1.0)
    else:
        result["VOL_RATIO"] = calc_volume_ratio(vol)
    result["MFI"] = calc_mfi(high, low, close, vol)

    return result


def calc_indicators_with_cache(symbol: str,
                                df: pd.DataFrame = None,
                                cache_dir: str = "data/processed",
                                data_dir: str = "data/data-by-stock",
                                force_recalc: bool = False) -> pd.DataFrame:
    """带缓存的指标计算"""
    cache_path = Path(cache_dir) / f"{symbol}.parquet"

    if not force_recalc and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        if "date" in cached.columns and df is not None and "date" in df.columns:
            cached_max = pd.to_datetime(cached["date"]).max()
            df_max = pd.to_datetime(df["date"]).max()
            if cached_max >= df_max:
                return cached

    if df is None:
        from atos.data.loader import load_stock_series
        df = load_stock_series(symbol, data_dir=data_dir)

    result = calc_all_indicators(df)
    if "date" in result.columns and not isinstance(result.index, pd.DatetimeIndex):
        result["date"] = pd.to_datetime(result["date"])
        result = result.set_index("date")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, compression="snappy", index=False)
    return result
