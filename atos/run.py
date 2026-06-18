"""ATOS 主入口

默认测试时间范围：2018-01-01 ~ 2020-04-30
（策略为震荡/熊市设计：2018 贸易战熊市 + 2019 震荡 + 2020 疫情初期）
默认测试集：中证 1000 成分股（流通市值 top 1000）
"""
import argparse
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 策略设计目标场景：震荡市 + 熊市（2018-2020.4 覆盖贸易战+疫情冲击）
DEFAULT_START = "2018-01-01"
DEFAULT_END = "2020-04-30"
# 默认股票池
DEFAULT_UNIVERSE = "CSI1000"


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main():
    parser = argparse.ArgumentParser(
        description="ATOS 策略回测（默认 2018-01-01 ~ 2020-04-30 震荡+熊市场景，CSI1000 股票池）"
    )
    parser.add_argument("--mode", choices=["single", "portfolio", "wf", "perturbation"],
                        default="single")
    parser.add_argument("--symbol", default="000001")
    parser.add_argument("--start", default=DEFAULT_START,
                        help=f"起始日期（默认 {DEFAULT_START}，策略目标场景）")
    parser.add_argument("--end", default=DEFAULT_END,
                        help=f"结束日期（默认 {DEFAULT_END}，策略目标场景）")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE,
                        choices=["all_A", "HS300", "CSI500", "CSI1000", "CYB_STAR_50", "HS300_CSI1000", "ALL", "COMBINED"],
                        help=f"股票池（默认 {DEFAULT_UNIVERSE}，CYB_STAR_50=创业板+科创板 50）")
    parser.add_argument("--universe-size", type=int, default=None,
                        help="限制股票数（默认 None = 全部股票池）")
    parser.add_argument("--config", default="config/params.yaml")
    parser.add_argument("--output", default=r"D:\claude-quant\reports")
    parser.add_argument("--scenarios", nargs="+", default=None,
                        help="场景标签：sideways/bear/bull/all")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("atos")
    logger.info(f"ATOS backtest: mode={args.mode}, symbol={args.symbol}, "
                 f"{args.start} -> {args.end}")
    logger.info(f"默认时间范围 {DEFAULT_START} ~ {DEFAULT_END} "
                 f"（策略为震荡/熊市设计）")
    logger.info(f"默认股票池: {args.universe}")

    # 加载配置
    from atos.config import load_config
    config = load_config(args.config)
    config.symbol = args.symbol

    if args.mode == "single":
        run_single_backtest(config, args)
    elif args.mode == "portfolio":
        run_portfolio_backtest(config, args)
    elif args.mode == "wf":
        run_walk_forward(config, args)
    elif args.mode == "perturbation":
        run_perturbation(config, args)


def run_single_backtest(config, args):
    """单标的回测"""
    import pandas as pd
    from atos.data import load_stock_series
    from atos.indicators import calc_all_indicators
    from atos.signals import generate_buy_signals
    from atos.backtest import BacktestEngine, generate_report

    logger = logging.getLogger("atos")

    # 1. 加载数据
    logger.info(f"Loading {args.symbol}...")
    df = load_stock_series(args.symbol, start=args.start, end=args.end)
    df_ind = calc_all_indicators(df)
    if "date" in df_ind.columns:
        df_ind["date"] = pd.to_datetime(df_ind["date"])
        df_ind = df_ind.set_index("date")

    # 2. 用 regime 替换 sig_final 的简化做法：直接按 regime 调 generate_buy_signals
    # 计算 regime
    from atos.regime import detect_full_regime
    regime_df = detect_full_regime(df_ind, config)

    # 在每个 regime 列生成信号
    logger.info("Generating signals...")
    sig_final = pd.Series(0, index=df_ind.index)
    for state in regime_df["effective_state"].unique():
        state_mask = regime_df["effective_state"] == state
        if state_mask.sum() == 0:
            continue
        state_df = df_ind.loc[state_mask]
        buy_signals = generate_buy_signals(state_df, state, config=config)
        sig_final.loc[state_df.index] = buy_signals["final"].values

    df_ind["sig_final"] = sig_final

    # 3. 回测
    logger.info("Running backtest...")
    engine = BacktestEngine(config)
    result = engine.run(market_df=df_ind)

    # 4. 输出
    logger.info("=" * 60)
    logger.info("[Returns]")
    for k in ["total_return", "annual_return", "n_years"]:
        logger.info(f"  {k}: {result.metrics.get(k, 0):.2%}" if k != "n_years" else
                     f"  {k}: {result.metrics.get(k, 0):.2f}")
    logger.info("[Risk]")
    for k in ["max_drawdown", "volatility", "sharpe", "sortino", "calmar"]:
        logger.info(f"  {k}: {result.metrics.get(k, 0):.4f}")
    logger.info("[Trades]")
    for k in ["n_trades", "win_rate", "profit_loss_ratio"]:
        v = result.metrics.get(k, 0)
        logger.info(f"  {k}: {v:.2%}" if k == "win_rate" else f"  {k}: {v:.2f}")

    # 5. 报告
    report_path = generate_report(result, output_dir=args.output)
    logger.info(f"Report saved to {report_path}")

    return result


def run_portfolio_backtest(config, args):
    """多标的组合回测（中文输出 + 客观交易表现数据）"""
    import pandas as pd
    from collections import Counter, defaultdict
    import numpy as np
    from atos.data import (
        load_processed, load_processed_benchmark, get_universe,
    )
    from atos.backtest import BacktestEngine, generate_report

    logger = logging.getLogger("atos")

    # 1. 加载大盘（用预计算 cache）
    logger.info("【1】加载大盘（缓存）...")
    market_ind = load_processed_benchmark(
        config.benchmark_name, start=args.start, end=args.end
    )
    if market_ind is None or len(market_ind) == 0:
        logger.error(f"  ✗ 大盘 {config.benchmark_name} 缓存不存在")
        return None
    logger.info(f"  ✓ 大盘 {len(market_ind)} 行")

    # 2. 加载股票池（按 args.universe 选择）
    logger.info(f"【2】选择股票池 {args.universe}...")
    liquidity_filter = getattr(config, "liquidity_filter_enabled", False)
    if args.universe == "CSI1000":
        from atos.data.universe import get_csi1000
        universe = get_csi1000(liquidity_filter=liquidity_filter)
    else:
        universe = get_universe(args.universe)
    if args.universe_size and args.universe_size > 0:
        universe = universe[:args.universe_size]
    logger.info(f"  待加载 {len(universe)} 只（流动性过滤: {liquidity_filter}）")

    logger.info("【3】加载股票数据（缓存）...")
    stock_data = {}
    skipped = []
    for sym in universe:
        try:
            df = load_processed(sym, start=args.start, end=args.end)
            if df is None or len(df) == 0:
                skipped.append((sym, "无数据"))
                continue
            if not isinstance(df.index, pd.DatetimeIndex):
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
            stock_data[sym] = df
        except Exception as e:
            skipped.append((sym, str(e)))
    logger.info(f"  ✓ 加载 {len(stock_data)} / {len(universe)} 只")
    if skipped:
        logger.info(f"  ⊘ 跳过 {len(skipped)} 只（无数据或读取失败）")
        if len(skipped) <= 10:
            for sym, reason in skipped:
                logger.info(f"    - {sym}: {reason}")

    # 4. 回测
    logger.info("【4】运行组合回测...")
    config.symbol = universe[0] if len(universe) > 0 else "000001"
    engine = BacktestEngine(config)
    result = engine.run(market_df=market_ind, stock_data=stock_data)

    # 4. 核心指标
    logger.info("=" * 60)
    logger.info("【核心指标】")
    m = result.metrics
    logger.info(f"  年化收益:  {m.get('annual_return', 0):.2%}")
    logger.info(f"  累计收益:  {m.get('total_return', 0):.2%}")
    logger.info(f"  最大回撤:  {m.get('max_drawdown', 0):.2%}")
    logger.info(f"  年化波动:  {m.get('volatility', 0):.2%}")
    logger.info(f"  夏普:     {m.get('sharpe', 0):.3f}")
    logger.info(f"  索提诺:   {m.get('sortino', 0):.3f}")
    logger.info(f"  胜率:     {m.get('win_rate', 0):.2%}")
    logger.info(f"  盈亏比:   {m.get('profit_loss_ratio', 0):.2f}")
    logger.info(f"  配对交易: {int(m.get('n_trades', 0))}")

    # 5. 年度收益
    eq = result.equity_curve
    yearly = eq.resample("YE").last().pct_change().dropna()
    logger.info("【年度收益】")
    for d, r in yearly.items():
        logger.info(f"  {d.year}: {r:.2%}")

    # 6. 按状态分组的交易表现
    if result.trades is not None and not result.trades.empty:
        paired_list = []
        for tid, g in result.trades.groupby("trade_id"):
            b = g[g["action"] == "BUY"]
            s = g[g["action"] == "SELL"]
            if not b.empty and not s.empty:
                entry = (b["price"] * b["shares"]).sum() / b["shares"].sum()
                exit_p = (s["price"] * s["shares"]).sum() / s["shares"].sum()
                paired_list.append({
                    "entry_regime": b["regime"].iloc[0] if "regime" in b.columns else "N/A",
                    "pnl_pct": (exit_p / entry - 1) if entry > 0 else 0,
                    "hold_days": (s["date"].iloc[0] - b["date"].iloc[0]).days,
                })

        if paired_list:
            logger.info("【按入场状态分组的交易表现】")
            regime_pnl = defaultdict(list)
            for p in paired_list:
                regime_pnl[p["entry_regime"]].append(p["pnl_pct"])
            for regime, pnls in sorted(regime_pnl.items(), key=lambda x: -len(x[1])):
                n = len(pnls)
                avg_pnl = np.mean(pnls)
                win_rate = sum(1 for p in pnls if p > 0) / n
                total = sum(pnls)
                logger.info(f"  {regime:<15} {n:>3} 笔 | 胜率 {win_rate:.0%} | "
                             f"平均 {avg_pnl:+.2%} | 累计 {total:+.2%}")

    # 7. 卖出原因分布
    if result.trades is not None and not result.trades.empty:
        sells = result.trades[result.trades["action"] == "SELL"]
        if len(sells) > 0 and "reason" in sells.columns:
            logger.info("【卖出原因分布】")
            reason_counter = Counter()
            for r in sells["reason"].fillna("未知"):
                if "移动止盈" in r:
                    reason_counter["移动止盈"] += 1
                elif "时间止损" in r:
                    reason_counter["时间止损"] += 1
                elif "硬止损" in r:
                    reason_counter["硬止损-8%"] += 1
                elif "浮盈" in r:
                    reason_counter["分批止盈"] += 1
                elif "CRASH" in r:
                    reason_counter["CRASH清仓"] += 1
                else:
                    reason_counter[r] += 1
            total = sum(reason_counter.values())
            for reason, n in sorted(reason_counter.items(), key=lambda x: -x[1]):
                logger.info(f"  {reason:<12} {n:>3} 次 ({n/total*100:>3.0f}%)")

    # 8. 持仓天数分布
    if result.trades is not None and not result.trades.empty:
        if "trade_id" in result.trades.columns:
            holding_days = []
            for tid, g in result.trades.groupby("trade_id"):
                b = g[g["action"] == "BUY"]
                s = g[g["action"] == "SELL"]
                if not b.empty and not s.empty:
                    days = (s["date"].iloc[0] - b["date"].iloc[0]).days
                    holding_days.append(days)
            if holding_days:
                hd = np.array(holding_days)
                logger.info("【持仓天数分布】")
                logger.info(f"  平均: {hd.mean():.1f} 天, 中位: {np.median(hd):.0f} 天, "
                            f"最大: {int(hd.max())} 天")
                for th in [1, 2, 3, 5, 10, 20, 30]:
                    if th > hd.max():
                        break
                    pct = (hd <= th).sum() / len(hd) * 100
                    logger.info(f"  <= {th} 天: {pct:.0f}%")

    # 9. 报告
    from atos.backtest.report import _short_uni
    report_path = generate_report(result, output_dir=args.output, config=config, universe=args.universe)
    logger.info(f"【报告已保存】{report_path}")
    logger.info("其他输出文件同目录 .csv / .png")
    return result


def run_walk_forward(config, args):
    """Walk-Forward 分析"""
    import pandas as pd
    from atos.data import load_stock_series
    from atos.indicators import calc_all_indicators
    from atos.backtest import walk_forward

    logger = logging.getLogger("atos")
    df = load_stock_series(args.symbol, start=args.start, end=args.end)
    df_ind = calc_all_indicators(df)
    if "date" in df_ind.columns:
        df_ind["date"] = pd.to_datetime(df_ind["date"])
        df_ind = df_ind.set_index("date")

    logger.info("Running walk-forward analysis...")
    result = walk_forward(df_ind, config, train_years=3, test_years=1)
    logger.info("=" * 60)
    logger.info("[Walk-Forward Folds]")
    for _, row in result["folds"].iterrows():
        logger.info(f"  Fold {int(row['fold'])}: "
                     f"train={row['train_period']}, test={row['test_period']}, "
                     f"annual={row['annual_return']:.2%}, "
                     f"sharpe={row['sharpe']:.2f}, "
                     f"max_dd={row['max_drawdown']:.2%}")
    logger.info("[Summary]")
    for k, v in result["summary"].items():
        logger.info(f"  {k}: {v:.2%}" if "return" in k or "dd" in k else f"  {k}: {v:.2f}")


def run_perturbation(config, args):
    """参数扰动测试"""
    import pandas as pd
    from atos.data import load_stock_series
    from atos.indicators import calc_all_indicators
    from atos.backtest import parameter_perturbation

    logger = logging.getLogger("atos")
    df = load_stock_series(args.symbol, start=args.start, end=args.end)
    df_ind = calc_all_indicators(df)
    if "date" in df_ind.columns:
        df_ind["date"] = pd.to_datetime(df_ind["date"])
        df_ind = df_ind.set_index("date")

    logger.info("Running parameter perturbation...")
    result = parameter_perturbation(config, df_ind, n_trials=10, perturbation=0.2)
    out = Path(args.output) / "perturbation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    logger.info(f"Perturbation results saved to {out}")
    logger.info(f"Total trials: {len(result)}")
    if len(result) > 0:
        logger.info("Fragile parameters (sorted by sharpe std):")
        if "sharpe" in result.columns:
            by_param = result.groupby("param")["sharpe"].agg(["mean", "std"])
            by_param = by_param.sort_values("std", ascending=False).head(5)
            for param, row in by_param.iterrows():
                logger.info(f"  {param}: mean={row['mean']:.2f}, std={row['std']:.2f}")


if __name__ == "__main__":
    main()
