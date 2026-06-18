"""选股器"""
import logging
import pandas as pd

from .factors import calc_all_factors
from .weight_schedule import get_factor_weights

logger = logging.getLogger("atos")


class StockSelector:
    """选股器"""

    def __init__(self, config):
        self.config = config
        self.factor_cache = {}  # {symbol: factors DataFrame}
        self.factor_weights = get_factor_weights("BULL")

    def _get_factors(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """获取/缓存单只股票的因子"""
        if symbol not in self.factor_cache:
            try:
                fdf = calc_all_factors(df)
                if not isinstance(fdf.index, pd.DatetimeIndex):
                    if "date" in df.columns:
                        fdf = fdf.set_index(pd.to_datetime(df["date"]))
                    else:
                        fdf.index = pd.to_datetime(fdf.index)
                self.factor_cache[symbol] = fdf
            except Exception as e:
                logger.debug(f"Factor calc fail for {symbol}: {e}")
                return None
        return self.factor_cache[symbol]

    def select(self, date, stock_data, state: str, top_n: int = 10) -> list:
        """选股主函数

        Args:
            date: 选股日期
            stock_data: {symbol: 含指标的 DataFrame}
            state: 当前市场状态
            top_n: 选 Top N

        Returns:
            选中的股票代码列表（按得分降序）
        """
        weights = get_factor_weights(state)
        if not weights:
            return []

        if isinstance(date, str):
            date_ts = pd.Timestamp(date)
        else:
            date_ts = date

        scores = {}
        for symbol, df in stock_data.items():
            if df is None or len(df) == 0:
                continue
            try:
                fdf = self._get_factors(symbol, df)
                if fdf is None:
                    continue
                if date_ts not in fdf.index:
                    valid = fdf.index[fdf.index <= date_ts]
                    if len(valid) == 0:
                        continue
                    actual_date = valid[-1]
                else:
                    actual_date = date_ts
                factor_today = fdf.loc[actual_date]
            except Exception as e:
                logger.debug(f"Skipping {symbol}: {e}")
                continue

            score = self._composite_score(factor_today.to_dict(), weights)
            if score is not None and not pd.isna(score):
                scores[symbol] = score

        if not scores:
            return []

        sorted_stocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [s[0] for s in sorted_stocks[:top_n]]

    def _composite_score(self, factor_values: dict, weights: dict):
        """计算综合得分"""
        score = 0.0
        weight_sum = 0.0
        for name, fv in factor_values.items():
            if name in weights and fv is not None and not pd.isna(fv):
                try:
                    score += weights[name] * float(fv)
                    weight_sum += weights[name]
                except (TypeError, ValueError):
                    continue
        if weight_sum == 0:
            return None
        if weight_sum < 0:
            return -score / abs(weight_sum)
        return score / weight_sum

    @staticmethod
    def cross_section_rank(factor_today: pd.Series) -> pd.Series:
        return factor_today.rank(pct=True) - 0.5
