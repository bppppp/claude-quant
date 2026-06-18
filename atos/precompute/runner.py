"""预计算主入口"""
import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="ATOS 预计算系统")
    parser.add_argument("--mode", choices=["indicators", "benchmark", "all"],
                        default="all")
    parser.add_argument("--universe", default="all_A",
                        help="股票池: all_A / HS300 / CSI1000")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None,
                        help="限制股票数（用于快速测试）")
    parser.add_argument("--cache-dir", default="data/processed/v1")
    args = parser.parse_args()

    from atos.precompute.parallel import ParallelPrecomputer
    from atos.data.universe import list_all_symbols

    pre = ParallelPrecomputer(
        cache_dir=args.cache_dir,
        n_workers=args.workers,
    )

    t0 = time.time()
    if args.mode in ("indicators", "all"):
        symbols = list_all_symbols()
        if args.limit:
            symbols = symbols[:args.limit]
        print(f"Precomputing {len(symbols)} symbols...")
        results = pre.precompute_all(symbols=symbols, force=False)
        n_ok = sum(1 for r in results if r and r.get("new_rows", 0) >= 0)
        n_new = sum(1 for r in results if r and r.get("new_rows", 0) > 0)
        print(f"  Done: {n_ok}/{len(results)}, new={n_new}, "
              f"avg_time={sum(r.get('compute_time', 0) for r in results)/max(1,len(results)):.3f}s")

    if args.mode in ("benchmark", "all"):
        print("\nPrecomputing benchmarks...")
        results = pre.precompute_benchmarks()
        for r in results:
            print(f"  {r}")

    print(f"\nTotal: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
