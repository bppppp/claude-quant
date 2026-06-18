#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ATOS MR v8 Report Generator — 2023-01-01 ~ 2025-12-31
Engine: atos/backtest/mr_v2.py (already contains v8 features)
"""
import sys, os, time, numpy as np, pandas as pd
from datetime import datetime
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from atos.backtest.mr_v2 import backtest_v2
from data.config import HS300, CYB_STAR_50, DISABLE_STOCK

# ── v8 params ──
START, END = "2023-01-01", "2025-12-31"
MAX_POSITIONS, POSITION_PCT = 22, 0.17
HOLD_DAYS, STOP_LOSS, TAKE_PROFIT = 8, -0.02, 0.30
INITIAL_CAPITAL = 1_000_000.0
trading_universe = sorted(set(HS300) | set(CYB_STAR_50) - DISABLE_STOCK)

print(f"=== ATOS MR v8 Backtest ===")
print(f"{START} ~ {END} | mp={MAX_POSITIONS} ps={POSITION_PCT} hd={HOLD_DAYS} sl={STOP_LOSS}")
t0 = time.time()

result = backtest_v2(
    start=START, end=END, universe_name="ALL",
    trading_universe_name=trading_universe,
    max_positions=MAX_POSITIONS, position_pct=POSITION_PCT,
    hold_days=HOLD_DAYS, take_profit=TAKE_PROFIT,
    stop_loss=STOP_LOSS, initial_capital=INITIAL_CAPITAL,
    verbose=True,
)

# ── Extract ──
eq_df = result["equity_curve"]
trades_df = result["trades"]
final_equity = result["final_equity"]
total_return = result["total_return"]
annual_return = result["annual_return"]
max_drawdown = result["max_drawdown"]
n_trades = result["n_trades"]
win_rate = result["win_rate"]
years = result["years"]
yearly_returns = result["yearly_returns"]

# ── Paired trades ──
paired = []
if not trades_df.empty:
    for sym, grp in trades_df.groupby("symbol"):
        b = grp[grp["action"] == "BUY"].sort_values("date")
        s = grp[grp["action"] == "SELL"].sort_values("date")
        for i in range(min(len(b), len(s))):
            pnl = s.iloc[i]["price"] / b.iloc[i]["price"] - 1
            d = (s.iloc[i]["date"] - b.iloc[i]["date"]).days
            r = s.iloc[i].get("reason", "?") if "reason" in s.columns else "?"
            paired.append({"pnl": pnl, "days": d, "reason": r, "yr": s.iloc[i]["date"].year})

pnl_arr = np.array([p["pnl"] for p in paired])
avg_pnl = np.mean(pnl_arr) if len(pnl_arr) > 0 else 0
median_pnl = np.median(pnl_arr) if len(pnl_arr) > 0 else 0
std_pnl = np.std(pnl_arr) if len(pnl_arr) > 0 else 0
wins = pnl_arr[pnl_arr > 0]
losses = pnl_arr[pnl_arr < 0]
avg_win = np.mean(wins) if len(wins) > 0 else 0
avg_loss = np.mean(np.abs(losses)) if len(losses) > 0 else 0
payoff = avg_win / avg_loss if avg_loss > 0 else 0
pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and abs(losses.sum()) > 0 else 0
skew = float(pd.Series(pnl_arr).skew()) if len(pnl_arr) > 2 else 0
kurt = float(pd.Series(pnl_arr).kurtosis()) if len(pnl_arr) > 3 else 0
max_w = float(np.max(pnl_arr)) if len(pnl_arr) > 0 else 0
max_l = float(np.min(pnl_arr)) if len(pnl_arr) > 0 else 0
pct_bw = (pnl_arr > 0.05).mean() * 100 if len(pnl_arr) > 0 else 0
pct_bl = (pnl_arr < -0.05).mean() * 100 if len(pnl_arr) > 0 else 0
avg_hold = np.mean([p["days"] for p in paired]) if paired else 0

# Consecutive
mw = ml = 0
cw = cl = 0
for v in (pnl_arr > 0).astype(int) if len(pnl_arr) > 0 else []:
    if v == 1: cw += 1; cl = 0; mw = max(mw, cw)
    else: cl += 1; cw = 0; ml = max(ml, cl)

daily = eq_df["equity"].pct_change().dropna()
vol = float(daily.std() * np.sqrt(252)) if len(daily) > 1 else 0
down = daily[daily < 0]
dvol = float(down.std() * np.sqrt(252)) if len(down) > 1 else 0
rf = 0.02
sharpe = (annual_return - rf) / vol if vol > 0 else 0
sortino = (annual_return - rf) / dvol if dvol > 0 else 0
calmar = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0

monthly = eq_df["equity"].resample("ME").last().pct_change().dropna()
mwr = (monthly > 0).mean() if len(monthly) > 0 else 0
mmax = float(monthly.max()) if len(monthly) > 0 else 0
mmin = float(monthly.min()) if len(monthly) > 0 else 0

avg_npos = float(eq_df["n_pos"].mean()) if "n_pos" in eq_df.columns else 0

# Max daily exposure
max_daily_exposure = 0.0
if not trades_df.empty and "n_pos" in eq_df.columns:
    for date in eq_df.index:
        pos_val = 0
        held_syms = set()
        for _, t in trades_df.iterrows():
            if t["action"] == "BUY" and t["date"] <= date:
                held_syms.add(t["symbol"])
            elif t["action"] == "SELL" and t["date"] <= date:
                held_syms.discard(t["symbol"])
        for sym in held_syms:
            sym_trades = trades_df[trades_df["symbol"] == sym]
            sym_buys = sym_trades[sym_trades["action"] == "BUY"].sort_values("date")
            sym_sells = sym_trades[sym_trades["action"] == "SELL"].sort_values("date")
            for i in range(min(len(sym_buys), len(sym_sells))):
                if sym_buys.iloc[i]["date"] <= date <= sym_sells.iloc[i]["date"]:
                    pos_val += sym_buys.iloc[i]["price"] * sym_buys.iloc[i]["shares"]
        if pos_val / eq_df.loc[date, "equity"] > max_daily_exposure:
            max_daily_exposure = pos_val / eq_df.loc[date, "equity"]

# Yearly stats
yr_stats = {}
for p in paired:
    y = p["yr"]
    yr_stats.setdefault(y, {"pnls": []})["pnls"].append(p["pnl"])

# Exit reasons
er_stats = []
if not trades_df.empty:
    sells = trades_df[trades_df["action"] == "SELL"]
    for reason, grp in sells.groupby("reason"):
        n = len(grp)
        avg = grp["pnl_pct"].mean() if "pnl_pct" in grp.columns else 0
        wr_r = (grp["pnl_pct"] > 0).mean() if "pnl_pct" in grp.columns else 0
        er_stats.append((reason, n, n / len(sells) * 100, avg, wr_r))
er_stats.sort(key=lambda x: -x[1])

# Holds by bucket
buckets = {"0-3d": [], "4-7d": [], "8-14d": [], "15-30d": []}
for p in paired:
    d = p["days"]
    if d <= 3: buckets["0-3d"].append(p["pnl"])
    elif d <= 7: buckets["4-7d"].append(p["pnl"])
    elif d <= 14: buckets["8-14d"].append(p["pnl"])
    else: buckets["15-30d"].append(p["pnl"])

# ── Benchmark ──
bm = pd.read_parquet("data/processed/v2/market/hs300.parquet")
if not isinstance(bm.index, pd.DatetimeIndex):
    bm["date"] = pd.to_datetime(bm["date"]); bm = bm.set_index("date")
bm_full_c = bm["close"]
bm_c = bm_full_c[bm_full_c.index >= START]
bm_c = bm_c[bm_c.index <= END]
bm_ann = (bm_c.iloc[-1] / bm_c.iloc[0]) ** (1 / years) - 1 if years > 0 else 0
bm_vol = float(bm_c.pct_change().dropna().std() * np.sqrt(252))
bm_dd = float(((bm_c - bm_c.cummax()) / bm_c.cummax()).min())
bm_m = bm_c.resample("ME").last().pct_change().dropna()
bm_mwr = (bm_m > 0).mean() if len(bm_m) > 0 else 0
bm_yr_s = bm_full_c.resample("YE").last().pct_change().dropna()
bm_yr = {d.year: float(v) for d, v in bm_yr_s.items()}

# ── Star helpers ──
def s(n): return "★" * n + "☆" * (5 - n)
def r_a(v):
    if v >= 0.25: return 5
    if v >= 0.15: return 4
    if v >= 0.08: return 3
    if v >= 0: return 2
    return 1
def r_d(v):
    if v >= -0.1: return 5
    if v >= -0.2: return 4
    if v >= -0.3: return 3
    return 2
def r_sh(v):
    if v >= 1.5: return 5
    if v >= 1: return 4
    if v >= 0.5: return 3
    return 2
def r_so(v):
    if v >= 2: return 5
    if v >= 1: return 4
    if v >= 0.5: return 3
    return 2
def r_ca(v):
    if v >= 2: return 5
    if v >= 1: return 4
    if v >= 0.5: return 3
    return 2
def r_w(v):
    if v >= 0.55: return 5
    if v >= 0.48: return 4
    if v >= 0.42: return 3
    return 2
def r_pa(v):
    if v >= 2.5: return 5
    if v >= 1.8: return 4
    if v >= 1.3: return 3
    return 2

# ── BUILD REPORT ──
rd = PROJECT_ROOT / "reports" / "ATOS_MR_v8"
rd.mkdir(parents=True, exist_ok=True)

as_date = eq_df.index[0].strftime("%Y-%m-%d")
ae_date = eq_df.index[-1].strftime("%Y-%m-%d")

rep = f"""# ATOS MR v8 策略回测报告 (新时段)

**{datetime.now().strftime("%Y-%m-%d %H:%M")}** | v8 深度优先排序 | mp={MAX_POSITIONS},ps={int(POSITION_PCT*100)}%,hd={HOLD_DAYS},sl={STOP_LOSS:.0%}
检测: ALL 1339 | 交易: HS300+CYB50 {len(trading_universe)}只

---

## v8 核心改进

**深度优先排序**: 同级信号中按跌幅深度排序。`sort(key=(prio, drop, RSI))`。
- 旧: 同优先级内按代码顺序 → 随机选股
- 新: 同优先级内跌幅最深优先 → 质量精选

三信号体系: MR主信号(prio=0) + MR副信号(prio=1) + 趋势突破(prio=2) + 突破前高(prio=3)

---

## 手续费与滑点

| 费用项 | 买入 | 卖出 | 说明 |
|--------|------|------|------|
| 佣金 | 0.025% | 0.025% | 最低5元 |
| 印花税 | 0% | 0.1% | 仅卖出 |
| 过户费 | 0.001% | 0.001% | |
| 滑点 | 0.1% | 0.1% | 买卖各0.1% |
| **单边** | **0.126%** | **0.226%** | |
| **双边合计** | | **~0.35%** | 每笔完整交易 |

---

## 核心指标

| 类别 | 指标 | 数值 | 评级 |
|------|------|------|------|
| 收益 | 年化 | **{annual_return:+.2%}** | {s(r_a(annual_return))} |
| 收益 | 累计 | **{total_return:+.1%}** | {s(r_a(total_return))} |
| 收益 | Active Premium | **{annual_return-bm_ann:+.1%}** | {s(5 if annual_return-bm_ann>0.15 else r_a(annual_return))} |
| 风险 | 最大回撤 | **{max_drawdown:+.2%}** | {s(r_d(max_drawdown))} |
| 风险 | 年化波动 | **{vol:.1%}** | {s(5 if vol<0.15 else 4)} |
| 风险调整 | Sharpe | **{sharpe:.2f}** | {s(r_sh(sharpe))} |
| 风险调整 | Sortino | **{sortino:.2f}** | {s(r_so(sortino))} |
| 风险调整 | Calmar | **{calmar:.2f}** | {s(r_ca(calmar))} |
| 交易 | 总交易对数 | **{n_trades}** | - |
| 交易 | 胜率 | **{win_rate:.1%}** | {s(r_w(win_rate))} |
| 交易 | 盈亏比 | **{payoff:.2f}** | {s(r_pa(payoff))} |
| 交易 | Profit Factor | **{pf:.2f}** | {s(5 if pf>2 else 4 if pf>1.5 else 3)} |
| 交易 | 最长连赢/连亏 | **{mw}**/**{ml}** | - |
| 分布 | 偏度 | **{skew:.2f}** | {s(5 if skew>1 else 4)} |
| 月度 | 月度胜率 | **{mwr:.1%}** | {s(5 if mwr>0.65 else 4 if mwr>0.55 else 3)} |
| 仓位 | 实际最大日曝光 | **{max_daily_exposure:.1%}** | 无杠杆 |
| 仓位 | 平均同时持仓 | **{avg_npos:.1f}只** | - |

---

## 年度对比

| 年度 | HS300 | MR v8 | 超额 | 胜率 | 笔数 | 评价 |
|------|-------|-------|------|------|------|------|
"""

for yr, ret in yearly_returns:
    b = bm_yr.get(yr, 0)
    diff = ret - b
    wr_yr = np.mean([1 if p > 0 else 0 for p in yr_stats.get(yr, {}).get("pnls", [])]) if yr in yr_stats else 0
    cnt = len(yr_stats.get(yr, {}).get("pnls", []))
    ev = "大幅跑赢" if diff > 0.05 else ("跑赢" if diff > 0 else "持平" if diff == 0 else "跑输")
    rep += f"| {yr} | {b:+.1%} | {ret:+.1%} | {diff:+.1%} | {wr_yr:.1%} | {cnt} | {ev} |\n"

rep += f"""
---

## 出场原因

| 原因 | 笔数 | 占比 | 平均收益 | 胜率 | 说明 |
|------|------|------|----------|------|------|
"""
rd_map = {"corp_action": "除权退出", "crash": "暴跌清仓", "sl": "止损", "time": "时间止损(主力)", "tp": "止盈"}
for reason, n, pct, avg, wr_r in er_stats:
    desc = rd_map.get(reason, reason)
    rep += f"| {reason} | {n} | {pct:.1f}% | {avg:+.2%} | {wr_r:.0%} | {desc} |\n"

rep += f"""
---

## 收益分布

| 指标 | 数值 | 说明 |
|------|------|------|
| 平均每笔 | {avg_pnl:+.3%} | - |
| 中位数 | {median_pnl:+.3%} | - |
| 标准差 | {std_pnl:.3%} | - |
| 偏度 | {skew:.2f} | 正偏=赚大亏小 |
| 最大单笔盈利 | {max_w:+.1%} | - |
| 最大单笔亏损 | {max_l:+.1%} | - |
| >+5%收益占比 | {pct_bw:.1f}% | - |
| <-5%亏损占比 | {pct_bl:.1f}% | - |
| 平均持仓 | {avg_hold:.1f}天 | - |

---

## 持仓天数 vs 胜率

| 持有 | 笔数 | 占比 | 胜率 | 平均收益 |
|------|------|------|------|----------|
"""

for bk, pnls in buckets.items():
    n_b = len(pnls); pct_b = n_b / len(paired) * 100 if paired else 0
    wr_b = np.mean([1 if p > 0 else 0 for p in pnls]) if pnls else 0
    avg_b = np.mean(pnls) if pnls else 0
    rep += f"| {bk} | {n_b} | {pct_b:.0f}% | {wr_b:.1%} | {avg_b:+.2%} |\n"

rep += f"""
---

## 版本演进

| 版本 | 参数 | 年化 | DD | Sharpe | 创新 |
|------|------|------|-----|--------|------|
| v5 Baseline | mp20,ps15%,hd10,sl2% | 19.8% | -16.6% | 1.02 | MR+流动性过滤 |
| v6 Dual | mp22,ps17%,hd8,sl2% | 39.2% | -13.9% | 1.78 | MR+趋势双信号 |
| v7 | mp22,ps17%,hd8,sl2% | 44.0% | -13.6% | 1.93 | +突破前高信号 |
| **v8 (新时段)** | **mp{MAX_POSITIONS},ps{int(POSITION_PCT*100)}%,hd{HOLD_DAYS},sl{abs(STOP_LOSS):.0f}%** | **{annual_return:+.1%}** | **{max_drawdown:+.1%}** | **{sharpe:.2f}** | **深度优先排序** |

---

## 仓位说明

{MAX_POSITIONS}只×{int(POSITION_PCT*100)}%={MAX_POSITIONS*int(POSITION_PCT*100)}%是名义值。实际受cash+BEAR乘0.2+SL快速退出约束:
- 平均持仓: {avg_npos:.1f}只
- 实际最大单日仓位: {max_daily_exposure:.1%}
- 策略**不使用杠杆**, 收益来自轮动

---

*报告由 ATOS MR v8 回测系统生成 | {as_date} ~ {ae_date}*
"""

report_path = rd / "ATOS_MR_v8_FULL_REPORT_new.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(rep)

print(f"\nReport saved: {report_path}")
print(f"\n=== v8 Summary ===")
print(f"Annual: {annual_return:+.2%} | DD: {max_drawdown:+.2%} | Sharpe: {sharpe:.2f} | WR: {win_rate:.1%} | Trades: {n_trades}")
for yr, ret in yearly_returns:
    print(f"  {yr}: {ret:+.2%}")
print(f"Time: {(time.time()-t0)/60:.1f} min")
