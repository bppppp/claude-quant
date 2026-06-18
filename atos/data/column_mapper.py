"""列名映射（中文 -> 英文）"""
import pandas as pd


COLUMN_MAPPING = {
    # 标识
    "日期": "date",
    "代码": "code",
    "名称": "name",
    "所属行业": "industry",
    # 行情
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "前收盘价": "prev_close",
    "振幅%": "amplitude",
    # 成交
    "成交量（股）": "volume",
    "成交额（元）": "amount",
    "换手率": "turnover",
    "量比": "vol_ratio",
    # 涨跌
    "涨幅%": "pct_change",
    "3日涨幅%": "pct_change_3d",
    "6日涨幅%": "pct_change_6d",
    "10日涨幅%": "pct_change_10d",
    "25日涨幅%": "pct_change_25d",
    "是否涨停": "is_limit_up",
    # 股本/市值
    "总股本（股）": "total_shares",
    "流通股本（股）": "float_shares",
    "总市值（元）": "mkt_cap_total",
    "流通市值（元）": "mkt_cap_float",
    # 估值
    "滚动市盈率": "pe_ttm",
    "市净率": "pb",
    "滚动市销率": "ps_ttm",
    # 均线
    "5日线": "MA5",
    "10日线": "MA10",
    "20日线": "MA20",
    "30日线": "MA30",
    "60日线": "MA60",
    "120日线": "MA120",
    "250日线": "MA250",
    # 状态
    "是否ST": "is_st",
    "是否融资融券": "is_margin",
    "上市时间": "list_date",
    "退市时间": "delist_date",
}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """列名标准化：中文 -> 英文"""
    df = df.rename(columns=COLUMN_MAPPING)
    required = ["date", "code", "name", "open", "high", "low", "close", "volume"]
    missing = [c for c in df.columns for r in required if c == r and False]
    return df
