"""数据清洗 - 5 项必做"""
import re
import numpy as np
import pandas as pd


def add_exchange_suffix(code: str) -> str:
    """6 位数字代码补交易所后缀"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    if code.startswith(("92", "83")):
        return f"{code}.BJ"
    return code


def _to_bool(v) -> bool:
    if pd.isna(v):
        return False
    return str(v).strip() == "是"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """5 项必做清洗

    1. 代码补后缀（在原 6 位上做，便于过滤北交所）
    2. 名称去全角空格
    3. 退市时间 '-' -> NaT
    4. 日期 -> pd.Timestamp
    5. 是/否 -> bool
    """
    df = df.copy()

    # 1. 先在原始 6 位代码上过滤北交所
    if "代码" in df.columns:
        raw_code = df["代码"].astype(str).str.zfill(6)
        df = df[~raw_code.str.startswith(("92", "83"))].copy()
        df["代码"] = df["代码"].astype(str).str.zfill(6).apply(add_exchange_suffix)

    # 2. 名称去全角空格
    if "名称" in df.columns:
        df["名称"] = df["名称"].astype(str).apply(lambda x: re.sub(r"\s+", "", x))

    # 3. 退市时间 '-' -> NaT
    if "退市时间" in df.columns:
        df["退市时间"] = pd.to_datetime(df["退市时间"], errors="coerce")

    # 4. 日期 -> pd.Timestamp
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])

    # 5. 是/否 -> bool
    for col in ["是否ST", "是否涨停", "是否融资融券"]:
        if col in df.columns:
            df[col] = df[col].map(_to_bool)

    # 6. 涨跌幅 -> 数值
    for col in ["涨幅%", "换手率", "振幅%", "量比",
                "3日涨幅%", "6日涨幅%", "10日涨幅%", "25日涨幅%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df
