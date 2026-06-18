"""涨跌停阈值（按板块区分）"""
import pandas as pd


def get_limit_threshold(row) -> float:
    """获取单只股票的涨停阈值

    主板 ±10%、创/科 ±20%、ST ±5%、北交所 ±30%
    """
    code = str(row.get("code", row.get("代码", "")))
    is_st = bool(row.get("is_st", row.get("是否ST", False)))

    if is_st:
        return 0.05
    raw = code.split(".")[0]
    if raw.startswith(("92", "83")):
        return 0.30
    if raw.startswith(("30", "688")):
        return 0.20
    return 0.10


def is_limit_up(row) -> bool:
    """判断是否涨停"""
    threshold = get_limit_threshold(row)
    pct = float(row.get("pct_change", row.get("涨幅%", 0)) or 0)
    return pct >= threshold * (1 - 0.003)


def is_limit_down(row) -> bool:
    """判断是否跌停"""
    threshold = get_limit_threshold(row)
    pct = float(row.get("pct_change", row.get("涨幅%", 0)) or 0)
    return pct <= -threshold * 0.97


def is_one_word_limit_up(row) -> bool:
    """一字涨停：open=high=low=close=涨停价"""
    try:
        o = float(row.get("open", row.get("开盘价", 0)))
        h = float(row.get("high", row.get("最高价", 0)))
        l = float(row.get("low", row.get("最低价", 0)))
        c = float(row.get("close", row.get("收盘价", 0)))
    except (TypeError, ValueError):
        return False
    return o == h == l == c and is_limit_up(row)


def is_suspended(row) -> bool:
    """停牌：成交量=0 且 价格不变"""
    try:
        v = float(row.get("volume", row.get("成交量（股）", 0)) or 0)
        c = float(row.get("close", row.get("收盘价", 0)) or 0)
        prev = float(row.get("prev_close", row.get("前收盘价", 0)) or 0)
    except (TypeError, ValueError):
        return False
    return v == 0 and c == prev
