"""回测报告生成（中文 Markdown）"""
import os
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd
import numpy as np


# 策略版本（命名规则：大版本号_小版本号，如 "2_v1"）
# 大版本：1=原 ATOS spec，2=第一次大升级
# 小版本：v1=baseline，v2-v5=迭代
STRATEGY_VERSION = "11_v1"

# 报告输出根目录
DEFAULT_REPORT_DIR = r"D:\claude-quant\reports"


def _safe_pct(v, default=0.0):
    try:
        return f"{float(v):.2%}"
    except (TypeError, ValueError):
        return f"{default:.2%}"


def _safe_num(v, digits=2, default=0.0):
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return f"{default:.{digits}f}"


def _short_uni(uni: str) -> str:
    """Universe 名短码化（用于文件名）"""
    mapping = {
        "HS300": "HS300",
        "CSI1000": "CSI1000",
        "CYB_STAR_50": "CYBSTAR",
        "ALL": "ALL",
        "COMBINED": "ALL",
    }
    return mapping.get(uni, uni.replace("/", "_"))


def _gen_filenames(output_dir: str, version: str, universe: str = ""):
    """生成版本化的文件名

    命名规则：
    - version 格式："{大版本}_{小版本}"，如 "2_v1"
    - universe: 股票池短码（HS300 / CSI1000 / CYBSTAR）
    - .md → reports/ 最外层
    - .csv / .png → reports/detail/

    例：report2_v1_HS300.md / detail/report2_v1_HS300_equity.csv
    """
    base = f"report{version}"
    if universe:
        base = f"{base}_{_short_uni(universe)}"
    detail_dir = Path(output_dir) / "detail"
    return {
        "md": Path(output_dir) / f"{base}.md",
        "equity_csv": detail_dir / f"{base}_equity.csv",
        "trades_csv": detail_dir / f"{base}_trades.csv",
        "chart": detail_dir / f"{base}_equity.png",
    }


def _extract_period(equity_curve) -> str:
    """从净值曲线提取回测期间"""
    if equity_curve is None or len(equity_curve) == 0:
        return ""
    try:
        start = equity_curve.index[0].strftime("%Y%m%d")
        end = equity_curve.index[-1].strftime("%Y%m%d")
        return f"{start}-{end}"
    except Exception:
        return ""


def _format_metric_table_md(metrics: dict) -> str:
    """格式化指标为 Markdown 表格"""
    lines = [
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 年化收益 | {_safe_pct(metrics.get('annual_return'))} |",
        f"| 累计收益 | {_safe_pct(metrics.get('total_return'))} |",
        f"| 回测年数 | {_safe_num(metrics.get('n_years'))} |",
        f"| 最大回撤 | {_safe_pct(metrics.get('max_drawdown'))} |",
        f"| 年化波动率 | {_safe_pct(metrics.get('volatility'))} |",
        f"| 下行波动率 | {_safe_pct(metrics.get('downside_vol'))} |",
        f"| VaR(95%) | {_safe_pct(metrics.get('var_95'))} |",
        f"| CVaR(95%) | {_safe_pct(metrics.get('cvar_95'))} |",
        f"| 回撤持续期 | {int(metrics.get('drawdown_duration', 0))} 天 |",
        f"| 夏普比率 | {_safe_num(metrics.get('sharpe'))} |",
        f"| 索提诺 | {_safe_num(metrics.get('sortino'))} |",
        f"| 卡尔玛 | {_safe_num(metrics.get('calmar'))} |",
    ]
    omega = metrics.get('omega', 0)
    lines.append(f"| Omega | {999.0 if omega >= 999 else omega:.2f} |")
    lines.append(f"| 配对交易数 | {int(metrics.get('n_trades', 0))} |")
    lines.append(f"| 买入次数 | {int(metrics.get('n_buys', 0))} |")
    lines.append(f"| 卖出次数 | {int(metrics.get('n_sells', 0))} |")
    lines.append(f"| 胜率 | {_safe_pct(metrics.get('win_rate'))} |")
    lines.append(f"| 盈亏比 | {_safe_num(metrics.get('profit_loss_ratio'))} |")
    lines.append(f"| 平均盈亏 | {_safe_pct(metrics.get('avg_pnl'))} |")
    lines.append(f"| 平均盈利 | {_safe_pct(metrics.get('avg_win'))} |")
    lines.append(f"| 平均亏损 | {_safe_pct(metrics.get('avg_loss'))} |")
    lines.append(f"| 最大单笔盈利 | {_safe_pct(metrics.get('max_pnl'))} |")
    lines.append(f"| 最大单笔亏损 | {_safe_pct(metrics.get('min_pnl'))} |")
    lines.append(f"| 最大连胜 | {int(metrics.get('max_consecutive_wins', 0))} |")
    lines.append(f"| 最大连亏 | {int(metrics.get('max_consecutive_losses', 0))} |")
    return "\n".join(lines)


def _format_yearly_md(equity_curve) -> str:
    """年度收益 Markdown 表格"""
    if equity_curve is None or len(equity_curve) == 0:
        return ""
    yearly = equity_curve.resample("YE").last().pct_change().dropna()
    if len(yearly) == 0:
        return ""
    lines = [
        "| 年份 | 收益 |",
        "| --- | --- |",
    ]
    for d, r in yearly.items():
        lines.append(f"| {d.year} | {_safe_pct(r)} |")
    return "\n".join(lines)


def _format_regime_pnl_md(paired_list) -> str:
    """按入场状态分组的交易表现 Markdown"""
    if not paired_list:
        return ""
    regime_pnl = defaultdict(list)
    for p in paired_list:
        regime_pnl[p["entry_regime"]].append(p["pnl_pct"])

    lines = [
        "| 入场状态 | 笔数 | 胜率 | 平均盈亏 | 累计盈亏 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for regime, pnls in sorted(regime_pnl.items(), key=lambda x: -len(x[1])):
        n = len(pnls)
        avg_pnl = np.mean(pnls)
        win_rate = sum(1 for p in pnls if p > 0) / n
        total = sum(pnls)
        lines.append(f"| {regime} | {n} | {win_rate:.0%} | {avg_pnl:+.2%} | {total:+.2%} |")
    return "\n".join(lines)


def _format_sell_reasons_md(sells) -> str:
    """卖出原因分布 Markdown"""
    if len(sells) == 0 or "reason" not in sells.columns:
        return ""
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
    if total == 0:
        return ""
    lines = [
        "| 卖出原因 | 次数 | 占比 |",
        "| --- | --- | --- |",
    ]
    for reason, n in sorted(reason_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| {reason} | {n} | {n/total*100:.0f}% |")
    return "\n".join(lines)


def _format_holding_days_md(holding_days) -> str:
    """持仓天数分布 Markdown"""
    if not holding_days:
        return ""
    hd = np.array(holding_days)
    lines = [
        f"**平均**: {hd.mean():.1f} 天, **中位**: {np.median(hd):.0f} 天, "
        f"**最大**: {int(hd.max())} 天\n",
        "| 持仓天数上限 | 占比 |",
        "| --- | --- |",
    ]
    for th in [1, 2, 3, 5, 10, 20, 30]:
        if th > hd.max():
            break
        pct = (hd <= th).sum() / len(hd) * 100
        lines.append(f"| <= {th} 天 | {pct:.0f}% |")
    return "\n".join(lines)


def generate_report(result, output_dir: str = None, config=None,
                    version: str = STRATEGY_VERSION,
                    universe: str = ""):
    """生成回测报告（Markdown 格式）

    Args:
        result: BacktestResult
        output_dir: 输出目录（默认 D:\\claude-quant\\reports）
        config: StrategyConfig
        version: 策略版本号（默认 V1）

    文件输出（位于 D:\\claude-quant\\reports\\report{V1}.*）：
    - reportV1.md         Markdown 报告（主）
    - detail/reportV1_equity.csv  净值曲线
    - detail/reportV1_trades.csv  交易明细
    - detail/reportV1_equity.png  净值/回撤/日收益图
    """
    # 默认输出到 D:\claude-quant\reports
    if output_dir is None:
        output_dir = DEFAULT_REPORT_DIR

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(Path(output_dir) / "detail", exist_ok=True)
    metrics = result.metrics

    # 计算回测期间
    period = _extract_period(getattr(result, "equity_curve", None))

    # 配对交易数据准备
    paired_list = []
    if result.trades is not None and not result.trades.empty:
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

    holding_days = []
    if result.trades is not None and not result.trades.empty:
        for tid, g in result.trades.groupby("trade_id"):
            b = g[g["action"] == "BUY"]
            s = g[g["action"] == "SELL"]
            if not b.empty and not s.empty:
                holding_days.append((s["date"].iloc[0] - b["date"].iloc[0]).days)

    sells_df = result.trades[result.trades["action"] == "SELL"] if result.trades is not None else None

    filenames = _gen_filenames(output_dir, version, universe)

    # 1. Markdown 报告（主）
    md_lines = [
        f"# ATOS {version} 量化策略回测报告",
        "",
        f"**策略版本**: {version}  ",
        f"**测试集**: {universe or '-'}  ",
        f"**回测期间**: {period.replace('-', ' ~ ')}  " if period else "**回测期间**: N/A  ",
        f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 收益指标",
        "",
        _format_metric_table_md(metrics),
        "",
    ]

    # 年度收益
    yearly_md = _format_yearly_md(getattr(result, "equity_curve", None))
    if yearly_md:
        md_lines.extend([
            "## 年度收益",
            "",
            yearly_md,
            "",
        ])

    # 按状态分组的交易表现
    md_lines.extend([
        "## 按入场状态分组的交易表现",
        "",
    ])
    regime_md = _format_regime_pnl_md(paired_list)
    if regime_md:
        md_lines.extend([regime_md, ""])
    else:
        md_lines.append("无完整配对交易\n")

    # 卖出原因分布
    md_lines.extend([
        "## 卖出原因分布",
        "",
    ])
    if sells_df is not None and len(sells_df) > 0:
        reason_md = _format_sell_reasons_md(sells_df)
        if reason_md:
            md_lines.extend([reason_md, ""])
        else:
            md_lines.append("无卖出记录\n")
    else:
        md_lines.append("无卖出记录\n")

    # 持仓天数分布
    md_lines.extend([
        "## 持仓天数分布",
        "",
    ])
    hd_md = _format_holding_days_md(holding_days)
    if hd_md:
        md_lines.extend([hd_md, ""])
    else:
        md_lines.append("无完整持仓记录\n")

    # 输出文件
    md_lines.extend([
        "## 输出文件",
        "",
        f"- Markdown 报告: `{filenames['md'].name}`",
    ])
    if len(result.equity_curve) > 0:
        md_lines.append(f"- 净值曲线 CSV: `{filenames['equity_csv'].name}`")
        md_lines.append(f"- 净值/回撤/日收益图: `{filenames['chart'].name}`")
    if result.trades is not None and not result.trades.empty:
        md_lines.append(f"- 交易明细 CSV: `{filenames['trades_csv'].name}`")
    md_lines.append("")

    # 写入 Markdown 文件
    with open(filenames["md"], "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # CSV 输出
    if len(result.equity_curve) > 0:
        result.equity_curve.to_csv(filenames["equity_csv"])
    if result.trades is not None and not result.trades.empty:
        result.trades.to_csv(filenames["trades_csv"], index=False)

    # 4. 可视化
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if len(result.equity_curve) > 0:
            fig, axes = plt.subplots(3, 1, figsize=(12, 10))

            # 净值曲线
            axes[0].plot(result.equity_curve.index, result.equity_curve.values,
                          label="策略净值", linewidth=1.5, color="steelblue")
            axes[0].axhline(y=1_000_000, color="gray", linestyle="--", alpha=0.5, label="初始资金")
            axes[0].set_title(f"ATOS {version} 策略净值曲线", fontsize=12, fontweight="bold")
            axes[0].set_ylabel("净值 (元)")
            axes[0].legend(loc="best")
            axes[0].grid(True, alpha=0.3)

            # 回撤
            cummax = result.equity_curve.cummax()
            dd = (result.equity_curve - cummax) / cummax
            axes[1].fill_between(dd.index, dd.values, 0, alpha=0.4, color="red")
            axes[1].set_title(f"回撤曲线（最大 {metrics.get('max_drawdown', 0):.2%}）",
                              fontsize=12, fontweight="bold")
            axes[1].set_ylabel("回撤")
            axes[1].grid(True, alpha=0.3)

            # 日收益分布
            daily_ret = result.equity_curve.pct_change().dropna()
            if len(daily_ret) > 0:
                axes[2].hist(daily_ret.values, bins=50, alpha=0.7, color="steelblue", edgecolor="black")
                axes[2].axvline(x=0, color="gray", linestyle="--", alpha=0.5)
                axes[2].set_title(f"日收益分布（μ={daily_ret.mean():.3%}, σ={daily_ret.std():.3%}）",
                                  fontsize=12, fontweight="bold")
                axes[2].set_xlabel("日收益率")
                axes[2].set_ylabel("频次")
                axes[2].grid(True, alpha=0.3)

            plt.tight_layout()
            plt.savefig(filenames["chart"], dpi=100)
            plt.close()
    except ImportError:
        pass

    return str(filenames["md"])
