"""数据校验器"""
import logging
import pandas as pd


class DataValidator:
    """数据校验器（针对金玥数据）"""

    def __init__(self):
        self.logger = logging.getLogger("atos")

    def validate(self, df: pd.DataFrame) -> bool:
        checks = [
            self._check_columns(df),
            self._check_no_missing_price(df),
            self._check_positive_price(df),
            self._check_high_low(df),
            self._check_volume(df),
        ]
        return all(checks)

    def _check_columns(self, df: pd.DataFrame) -> bool:
        required = ["date", "code", "open", "high", "low", "close", "volume"]
        ok = all(c in df.columns for c in required)
        if not ok:
            self.logger.error("Missing required columns")
        return ok

    def _check_no_missing_price(self, df: pd.DataFrame) -> bool:
        return df[["open", "high", "low", "close"]].notna().all().all()

    def _check_positive_price(self, df: pd.DataFrame) -> bool:
        return (df[["open", "high", "low", "close"]] > 0).all().all()

    def _check_high_low(self, df: pd.DataFrame) -> bool:
        cond1 = (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        cond2 = (df["low"] <= df[["open", "close"]].min(axis=1)).all()
        return cond1 and cond2

    def _check_volume(self, df: pd.DataFrame) -> bool:
        return (df["volume"] >= 0).all()
