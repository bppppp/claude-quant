"""并行预计算器 - 多股票批量计算"""
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from multiprocessing import cpu_count

import pandas as pd

from atos.data.universe import list_all_symbols
from atos.data.benchmark_loader import load_benchmark, VALID_BENCHMARKS


def _precompute_one_symbol(args):
    """worker: 单只股票预计算（顶层函数以支持 pickle）"""
    symbol, cache_dir, data_dir = args
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from atos.precompute.incremental import IncrementalUpdater
    updater = IncrementalUpdater(cache_dir=cache_dir)
    return symbol, updater.update_symbol(symbol, data_dir=data_dir, force=False)


def _precompute_one_benchmark(args):
    name, cache_dir, data_dir = args
    import sys
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from atos.indicators.pipeline import calc_all_indicators
    from atos.data.storage import save_optimized

    start = time.time()
    from pathlib import Path as P
    cache_path = P(cache_dir) / "market" / f"{name}.parquet"
    if cache_path.exists():
        return name, {"new_rows": 0, "compute_time": 0, "cached": True}

    df = load_benchmark(name, data_dir=data_dir)
    if len(df) == 0:
        return name, {"new_rows": 0, "compute_time": 0, "cached": False}

    result = calc_all_indicators(df)
    if "date" in result.columns:
        result["date"] = pd.to_datetime(result["date"])
        result = result.set_index("date")
    save_optimized(result, cache_path)
    return name, {"new_rows": len(df), "compute_time": time.time() - start, "cached": False}


class ParallelPrecomputer:
    """并行预计算器"""

    def __init__(self, config=None, cache_dir: str = "data/processed/v1",
                  data_dir: str = "data/data-by-stock",
                  benchmark_dir: str = "data/data-benchmark",
                  n_workers: int = None):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.data_dir = data_dir
        self.benchmark_dir = benchmark_dir
        self.n_workers = n_workers or max(1, min(4, cpu_count() - 1))

    def precompute_all(self, symbols: list = None, force: bool = False,
                        use_threads: bool = True) -> list:
        """预计算所有股票"""
        if symbols is None:
            symbols = list_all_symbols(self.data_dir)
        if not force:
            symbols = [s for s in symbols
                       if not (self.cache_dir / "stock" / f"{s}.parquet").exists()]
        if not symbols:
            return []
        print(f"Precomputing {len(symbols)} symbols with {self.n_workers} workers...")

        results = []
        args_list = [(s, str(self.cache_dir), self.data_dir) for s in symbols]
        executor_cls = ThreadPoolExecutor if use_threads else ProcessPoolExecutor
        with executor_cls(max_workers=self.n_workers) as executor:
            futures = {executor.submit(_precompute_one_symbol, a): a[0] for a in args_list}
            done_count = 0
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    symbol, result = future.result(timeout=600)
                    results.append(result)
                except Exception as e:
                    print(f"  Failed: {sym}: {e}")
                done_count += 1
                if done_count % 50 == 0 or done_count == len(args_list):
                    print(f"  Progress: {done_count}/{len(args_list)}")
        return results

    def precompute_benchmarks(self, names: list = None) -> list:
        """预计算所有大盘指数"""
        if names is None:
            names = list(VALID_BENCHMARKS)
        results = []
        args_list = [(n, str(self.cache_dir), self.benchmark_dir) for n in names]
        with ThreadPoolExecutor(max_workers=min(4, len(args_list))) as executor:
            futures = {executor.submit(_precompute_one_benchmark, a): a[0] for a in args_list}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    n, result = future.result(timeout=120)
                    results.append(result)
                except Exception as e:
                    print(f"  Failed benchmark {name}: {e}")
        return results

    def precompute_daily_selection(self, date: str) -> pd.DataFrame:
        """预计算某日全市场选股日榜"""
        from atos.selection.selector import StockSelector
        from atos.data.loader import load_daily_cross_section

        daily = load_daily_cross_section(date, data_dir="data/data-by-day")

        factor_dict = {}
        for symbol in daily["code"]:
            cache_path = self.cache_dir / "stock" / f"{symbol}.parquet"
            if cache_path.exists():
                fdf = pd.read_parquet(cache_path)
                if date in fdf.index:
                    factor_dict[symbol] = fdf.loc[date]

        if not factor_dict:
            return pd.DataFrame()

        regime = self.get_regime_at_date(date)
        selector = StockSelector(self.config)
        weights = selector.factor_weights

        results = []
        for symbol, fvals in factor_dict.items():
            score = selector._composite_score(fvals.to_dict() if hasattr(fvals, "to_dict") else fvals, weights)
            name = daily.loc[daily["code"] == symbol, "name"].iloc[0] if not daily[daily["code"] == symbol].empty else symbol
            results.append({
                "symbol": symbol,
                "name": name,
                "composite_score": score,
                "regime": regime,
            })
        day_df = pd.DataFrame(results)
        day_df.to_parquet(self.cache_dir / "selection" / f"{date}.parquet")
        return day_df

    def get_regime_at_date(self, date: str) -> str:
        regime_path = self.cache_dir / "regime" / f"{date}.parquet"
        if regime_path.exists():
            df = pd.read_parquet(regime_path)
            return str(df.loc[0, "effective_state"]) if not df.empty else "SIDEWAYS"
        return "SIDEWAYS"
