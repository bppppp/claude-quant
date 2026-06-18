"""指标层单元测试"""
import numpy as np
import pandas as pd
import pytest

from atos.indicators.trend import calc_ma, calc_ema, calc_macd, calc_dmi_adx
from atos.indicators.trend import calc_ma_alignment, calc_ma_convergence
from atos.indicators.momentum import calc_kdj, calc_rsi, calc_cci
from atos.indicators.channels import calc_boll, calc_atr, calc_donchian
from atos.indicators.volume import calc_obv, calc_vwap, calc_mfi, calc_volume_ratio
from atos.indicators.pipeline import calc_all_indicators


@pytest.fixture
def sample_df():
    np.random.seed(42)
    n = 250
    close = pd.Series(np.cumsum(np.random.randn(n) * 0.5) + 100,
                      index=pd.date_range("2023-01-01", periods=n))
    return pd.DataFrame({
        "date": close.index,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + np.abs(np.random.randn(n)) * 0.5,
        "low": close - np.abs(np.random.randn(n)) * 0.5,
        "close": close,
        "volume": np.random.randint(1_000_000, 10_000_000, n),
    })


def test_calc_ma_default_periods(sample_df):
    """默认 MA 周期应为 [5,10,20,60,120,250]"""
    ma = calc_ma(sample_df["close"])
    assert set(ma.columns) == {"MA5", "MA10", "MA20", "MA60", "MA120", "MA250"}


def test_calc_ma_5day_average(sample_df):
    """MA5[i] = mean(close[i-4:i+1])"""
    ma5 = calc_ma(sample_df["close"], periods=[5])["MA5"]
    expected = sample_df["close"].rolling(5, min_periods=1).mean()
    assert np.allclose(ma5.values, expected.values)


def test_calc_macd_columns(sample_df):
    """MACD 输出应包含 DIF, DEA, MACD"""
    m = calc_macd(sample_df["close"])
    assert {"DIF", "DEA", "MACD"} <= set(m.columns)
    # MACD = 2 * (DIF - DEA)
    assert np.allclose(m["MACD"], 2 * (m["DIF"] - m["DEA"]))


def test_calc_dmi_adx_range(sample_df):
    """DMI/ADX 数值应在合理范围"""
    dmi = calc_dmi_adx(sample_df["high"], sample_df["low"], sample_df["close"])
    assert {"PDI", "NDI", "ADX", "DX"} <= set(dmi.columns)
    # PDI, NDI 应在 [0, 100] 附近
    assert (dmi["PDI"] >= 0).all() and (dmi["PDI"] <= 100).all()
    assert (dmi["NDI"] >= 0).all() and (dmi["NDI"] <= 100).all()
    assert (dmi["ADX"] >= 0).all()


def test_calc_kdj_range(sample_df):
    """KDJ 数值应在 [0, 100]（K/D 允许轻微超界 due to EWM smoothing）"""
    kdj = calc_kdj(sample_df["high"], sample_df["low"], sample_df["close"])
    assert kdj["K"].dropna().between(-1, 101).all()
    assert kdj["D"].dropna().between(-1, 101).all()
    assert kdj["J"].dropna().between(-150, 250).all()  # J 可超界


def test_calc_rsi_range(sample_df):
    """RSI 应在 [0, 100]"""
    rsi = calc_rsi(sample_df["close"])
    for col in rsi.columns:
        assert rsi[col].dropna().between(0, 100).all()


def test_calc_boll_ordering(sample_df):
    """布林带：UP >= MID >= DOWN"""
    boll = calc_boll(sample_df["close"])
    # 早期可能有 NaN，drop 后比较
    valid = boll.dropna()
    assert (valid["BOLL_UP"] >= valid["BOLL_MID"]).all()
    assert (valid["BOLL_MID"] >= valid["BOLL_DOWN"]).all()
    # %b 应在 [0, 1] 附近（可能略超界）
    assert valid["BOLL_PB"].between(-1, 2).all()


def test_calc_atr_positive(sample_df):
    """ATR 始终为正"""
    atr = calc_atr(sample_df["high"], sample_df["low"], sample_df["close"])
    assert (atr > 0).all()
    # ATR = 真实波幅的 Wilder 平滑
    prev_close = sample_df["close"].shift(1)
    tr1 = sample_df["high"] - sample_df["low"]
    tr2 = (sample_df["high"] - prev_close).abs()
    tr3 = (sample_df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    expected = tr.ewm(alpha=1/14, adjust=False).mean()
    assert np.allclose(atr.values[13:], expected.values[13:])


def test_calc_donchian_ordering(sample_df):
    """Donchian：UP >= LOW"""
    dc = calc_donchian(sample_df["high"], sample_df["low"])
    assert (dc["DC_UP"] >= dc["DC_LOW"]).all()
    assert np.allclose(dc["DC_MID"], (dc["DC_UP"] + dc["DC_LOW"]) / 2)


def test_calc_obv_cumsum(sample_df):
    """OBV 应为方向 * 成交量的累计和"""
    obv = calc_obv(sample_df["close"], sample_df["volume"])
    direction = np.sign(sample_df["close"].diff()).fillna(0)
    expected = (direction * sample_df["volume"]).cumsum()
    assert np.allclose(obv.values, expected.values)


def test_calc_vwap_positive(sample_df):
    """VWAP 应为正"""
    vwap = calc_vwap(sample_df["high"], sample_df["low"], sample_df["close"],
                     sample_df["volume"])
    assert (vwap > 0).all()


def test_calc_mfi_range(sample_df):
    """MFI 应在 [0, 100]"""
    mfi = calc_mfi(sample_df["high"], sample_df["low"], sample_df["close"],
                   sample_df["volume"])
    assert mfi.between(0, 100).dropna().all()


def test_pipeline_completeness(sample_df):
    """calc_all_indicators 应输出完整列集"""
    result = calc_all_indicators(sample_df)
    expected = ["MA5", "MA20", "MA60", "MA120", "DIF", "DEA", "MACD",
                "K", "D", "J", "RSI6", "RSI12", "RSI24", "CCI",
                "BOLL_MID", "BOLL_UP", "BOLL_DOWN", "ATR",
                "PDI", "NDI", "ADX", "DC_UP", "DC_LOW",
                "OBV", "MFI", "VWAP", "MA_ALIGN", "MA_CONV"]
    for col in expected:
        assert col in result.columns, f"Missing: {col}"


def test_ma_alignment_range(sample_df):
    """均线排列强度应在 [0, 1]"""
    align = calc_ma_alignment(sample_df["close"])
    assert align.between(0, 1).all()


def test_ma_convergence_positive(sample_df):
    """粘合度应 >= 0"""
    conv = calc_ma_convergence(sample_df["close"])
    assert (conv >= 0).all()
