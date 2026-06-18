"""大盘指数数据加载器"""
from pathlib import Path
import pandas as pd


VALID_BENCHMARKS = (
    "hs300", "sse_index", "sse50", "csi500", "csi1000",
    "csi_consumer", "csi_pharma", "csi_finance",
    "chinext", "szse_component",
)


def load_benchmark(name: str = "hs300",
                    start: str = None,
                    end: str = None,
                    data_dir: str = "data/data-benchmark") -> pd.DataFrame:
    """加载大盘指数数据"""
    if name not in VALID_BENCHMARKS:
        raise ValueError(f"Unknown benchmark: {name}. Valid: {VALID_BENCHMARKS}")

    base_dir = Path(data_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"Benchmark dir not found: {base_dir}")

    dfs = []
    for year_dir in sorted(base_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        file_path = year_dir / f"{name}_{year_dir.name}_benchmark.csv"
        if file_path.exists():
            year_df = pd.read_csv(file_path)
            dfs.append(year_df)

    if not dfs:
        raise FileNotFoundError(f"No data for benchmark: {name}")

    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]

    return df.reset_index(drop=True)
