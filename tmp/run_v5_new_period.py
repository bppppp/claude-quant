# -*- coding: utf-8 -*-
"""ATOS MR v5 - Test on 2023-01-01 ~ 2026-05-31, generate report"""
import sys
sys.path.insert(0, r'D:\claude-quant')
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime
from collections import Counter, defaultdict

from atos.backtest.mr_v2 import backtest_v2
from atos.data.universe import get_universe
from data.config import HS300, CYB_STAR_50, DISABLE_STOCK

# Config
START = '2023-01-01'
END = '2026-05-31'
UNIVERSE_NAME = 'ALL'
INITIAL_CAPITAL = 1_000_000.0

# Trading pool: HS300 + CYB_STAR_50 (352 stocks, same as v5)
trading_universe = sorted(set(HS300) | set(CYB_STAR_50) - DISABLE_STOCK)

print(f'=== ATOS MR v5 New Period Backtest ===')
print(f'Period: {START} ~ {END}')
print(f'Detection pool: {UNIVERSE_NAME}')
print(f'Trading pool: HS300 + CYB_STAR_50 ({len(trading_universe)} stocks)')
print()

t0 = time.time()
result = backtest_v2(
    start=START,
    end=END,
    universe_name=UNIVERSE_NAME,
    trading_universe_name=trading_universe,
    max_positions=20,
    position_pct=0.15,
    hold_days=10,
    take_profit=0.30,
    stop_loss=-0.02,
    initial_capital=INITIAL_CAPITAL,
    verbose=True,
)
elapsed = time.time() - t0
print(f'\nBacktest completed in {elapsed:.1f}s')

# ===== Build Report =====
eq_df = result['equity_curve']
trades_df = result['trades']
final_equity = result['final_equity']
total_return = result['total_return']
annual_return = result['annual_return']
max_drawdown = result['max_drawdown']
n_trades = result['n_trades']
win_rate = result['win_rate']
years = result['years']
yearly_returns = result['yearly_returns']

# Actual date range
actual_start = eq_df.index[0].strftime('%Y-%m-%d')
actual_end = eq_df.index[-1].strftime('%Y-%m-%d')

# ===== Compute additional metrics =====

# Paired trades for pnl analysis
paired_pnls = []
if not trades_df.empty:
    for sym, grp in trades_df.groupby('symbol'):
        b = grp[grp['action'] == 'BUY'].sort_values('date')
        s = grp[grp['action'] == 'SELL'].sort_values('date')
        for i in range(min(len(b), len(s))):
            paired_pnls.append(s.iloc[i]['price'] / b.iloc[i]['price'] - 1)

pnl_arr = np.array(paired_pnls) if paired_pnls else np.array([])
avg_pnl = np.mean(pnl_arr) if len(pnl_arr) > 0 else 0
median_pnl = np.median(pnl_arr) if len(pnl_arr) > 0 else 0
std_pnl = np.std(pnl_arr) if len(pnl_arr) > 0 else 0

# Payoff ratio
wins = pnl_arr[pnl_arr > 0] if len(pnl_arr) > 0 else np.array([])
losses = pnl_arr[pnl_arr < 0] if len(pnl_arr) > 0 else np.array([])
avg_win = np.mean(wins) if len(wins) > 0 else 0
avg_loss = np.mean(np.abs(losses)) if len(losses) > 0 else 0
payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0
profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and abs(losses.sum()) > 0 else 0

# Skewness / Kurtosis
skewness = float(pd.Series(pnl_arr).skew()) if len(pnl_arr) > 2 else 0
kurtosis = float(pd.Series(pnl_arr).kurtosis()) if len(pnl_arr) > 3 else 0

# Max single win/loss
max_win = float(np.max(pnl_arr)) if len(pnl_arr) > 0 else 0
max_loss = float(np.min(pnl_arr)) if len(pnl_arr) > 0 else 0

# % >5% win / <-5% loss
pct_big_win = (pnl_arr > 0.05).mean() * 100 if len(pnl_arr) > 0 else 0
pct_big_loss = (pnl_arr < -0.05).mean() * 100 if len(pnl_arr) > 0 else 0

# Consecutive wins/losses
if len(pnl_arr) > 0:
    wins_arr = (pnl_arr > 0).astype(int)
    max_consec_wins = max_consec_losses = 0
    cur_w = cur_l = 0
    for v in wins_arr:
        if v == 1:
            cur_w += 1; cur_l = 0
            max_consec_wins = max(max_consec_wins, cur_w)
        else:
            cur_l += 1; cur_w = 0
            max_consec_losses = max(max_consec_losses, cur_l)
else:
    max_consec_wins = max_consec_losses = 0

# Volatility (annualized)
daily_returns = eq_df['equity'].pct_change().dropna()
volatility = float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 1 else 0

# Sortino ratio
downside = daily_returns[daily_returns < 0]
downside_vol = float(downside.std() * np.sqrt(252)) if len(downside) > 1 else 0
sortino = (annual_return - 0.02) / downside_vol if downside_vol > 0 else 0  # 2% risk-free

# Sharpe ratio
sharpe = (annual_return - 0.02) / volatility if volatility > 0 else 0

# Calmar ratio
calmar = annual_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0

# Monthly win rate
monthly = eq_df['equity'].resample('ME').last().pct_change().dropna()
monthly_win_rate = (monthly > 0).mean() if len(monthly) > 0 else 0
max_monthly_win = float(monthly.max()) if len(monthly) > 0 else 0
max_monthly_loss = float(monthly.min()) if len(monthly) > 0 else 0

# Holding days
holding_days = []
if not trades_df.empty:
    for sym, grp in trades_df.groupby('symbol'):
        b = grp[grp['action'] == 'BUY'].sort_values('date')
        s = grp[grp['action'] == 'SELL'].sort_values('date')
        for i in range(min(len(b), len(s))):
            holding_days.append((s.iloc[i]['date'] - b.iloc[i]['date']).days)
avg_hold = np.mean(holding_days) if holding_days else 0

# Exit reason analysis
exit_reason_stats = []
if not trades_df.empty:
    sells = trades_df[trades_df['action'] == 'SELL']
    for reason, grp in sells.groupby('reason'):
        n = len(grp)
        pct = n / len(sells) * 100
        if 'pnl_pct' in grp.columns:
            avg_pnl_reason = grp['pnl_pct'].mean()
            win_rate_reason = (grp['pnl_pct'] > 0).mean() if len(grp) > 0 else 0
        else:
            avg_pnl_reason = 0
            win_rate_reason = 0
        exit_reason_stats.append({
            'reason': reason, 'count': n, 'pct': pct,
            'avg_pnl': avg_pnl_reason, 'win_rate': win_rate_reason
        })
exit_reason_stats.sort(key=lambda x: -x['count'])

# ===== Star ratings =====
def star_rating(metric_name, value):
    """Rate metrics on 1-5 stars"""
    if metric_name == 'annual_return':
        if value >= 0.25: return 5
        if value >= 0.15: return 4
        if value >= 0.08: return 3
        if value >= 0.00: return 2
        return 1
    elif metric_name == 'total_return':
        if value >= 1.0: return 5
        if value >= 0.5: return 4
        if value >= 0.2: return 3
        if value >= 0.0: return 2
        return 1
    elif metric_name == 'max_drawdown':
        if value >= -0.10: return 5
        if value >= -0.20: return 4
        if value >= -0.30: return 3
        if value >= -0.40: return 2
        return 1
    elif metric_name == 'volatility':
        if value <= 0.15: return 5
        if value <= 0.20: return 4
        if value <= 0.25: return 3
        if value <= 0.30: return 2
        return 1
    elif metric_name == 'sharpe':
        if value >= 1.5: return 5
        if value >= 1.0: return 4
        if value >= 0.5: return 3
        if value >= 0.0: return 2
        return 1
    elif metric_name == 'sortino':
        if value >= 2.0: return 5
        if value >= 1.0: return 4
        if value >= 0.5: return 3
        if value >= 0.0: return 2
        return 1
    elif metric_name == 'calmar':
        if value >= 2.0: return 5
        if value >= 1.0: return 4
        if value >= 0.5: return 3
        if value >= 0.0: return 2
        return 1
    elif metric_name == 'win_rate':
        if value >= 0.55: return 5
        if value >= 0.48: return 4
        if value >= 0.42: return 3
        if value >= 0.35: return 2
        return 1
    elif metric_name == 'payoff_ratio':
        if value >= 2.5: return 5
        if value >= 1.8: return 4
        if value >= 1.3: return 3
        if value >= 1.0: return 2
        return 1
    elif metric_name == 'profit_factor':
        if value >= 2.5: return 5
        if value >= 1.5: return 4
        if value >= 1.0: return 3
        if value >= 0.8: return 2
        return 1
    elif metric_name == 'skewness':
        if value >= 1.0: return 5
        if value >= 0.5: return 4
        if value >= 0.0: return 3
        if value >= -0.5: return 2
        return 1
    elif metric_name == 'monthly_win_rate':
        if value >= 0.65: return 5
        if value >= 0.55: return 4
        if value >= 0.45: return 3
        if value >= 0.35: return 2
        return 1
    return 3

def stars_str(n):
    return '★' * n + '☆' * (5 - n)

# ===== HS300 benchmark data for comparison =====
# HS300 annual returns for reference (actual index data)
# We'll compute from the benchmark file
try:
    # Load full benchmark for yearly comparison (need previous year-end for pct_change)
    bm_full = pd.read_parquet('data/processed/v2/market/hs300.parquet')
    if not isinstance(bm_full.index, pd.DatetimeIndex):
        if 'date' in bm_full.columns:
            bm_full['date'] = pd.to_datetime(bm_full['date'])
            bm_full = bm_full.set_index('date')
    bm = bm_full[bm_full.index >= START]
    bm = bm[bm.index <= END]
    bm_close = bm['close']
    # Use full data for yearly returns (need Dec 2022 for 2023 pct_change)
    bm_full_close = bm_full['close']
    bm_yearly_series = bm_full_close.resample('YE').last().pct_change().dropna()
    # Dict: year -> return
    bm_yearly = {d.year: float(v) for d, v in bm_yearly_series.items()}
    bm_annual_return = (bm_close.iloc[-1] / bm_close.iloc[0]) ** (1/years) - 1 if years > 0 else 0
    bm_vol = float(bm_close.pct_change().dropna().std() * np.sqrt(252))
    bm_cummax = bm_close.cummax()
    bm_max_dd = float(((bm_close - bm_cummax) / bm_cummax).min())
    bm_monthly = bm_close.resample('ME').last().pct_change().dropna()
    bm_monthly_win = (bm_monthly > 0).mean()
    bm_sharpe = (bm_annual_return - 0.02) / bm_vol if bm_vol > 0 else 0
except Exception as e:
    print(f'Warning: Could not compute benchmark: {e}')
    bm_yearly = {}
    bm_annual_return = 0
    bm_vol = 0
    bm_max_dd = 0
    bm_monthly_win = 0
    bm_sharpe = 0

# ===== Generate Markdown Report =====
NL = '\n'
report = f'# ATOS MR v5 策略回测完整报告 (新时段)' + NL
report += NL
report += f'**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}' + NL
report += f'**检测池**: ALL 1339 只 (HS300+CSI1000+CYB50)' + NL
report += f'**交易池**: HS300 + CYB_STAR_50 ({len(trading_universe)} 只)' + NL
report += f'**回测区间**: {actual_start} ~ {actual_end}' + NL
report += f'**初始资金**: {INITIAL_CAPITAL:,.0f}' + NL
report += NL
report += '---' + NL + NL
report += '## 1. 核心指标' + NL + NL
report += '| 类别 | 指标 | 数值 | 评级 |' + NL
report += '|------|------|------|------|' + NL
report += f'| 收益 | 年化收益 | **{annual_return:+.2%}** | {stars_str(star_rating("annual_return", annual_return))} |' + NL
report += f'| 收益 | 累计收益 | **{total_return:+.2%}** | {stars_str(star_rating("total_return", total_return))} |' + NL
report += f'| 收益 | Active Premium vs HS300 | **{annual_return-bm_annual_return:+.1%}** | {stars_str(5 if annual_return-bm_annual_return > 0.10 else 3)} |' + NL
report += f'| 风险 | 最大回撤 | **{max_drawdown:+.2%}** | {stars_str(star_rating("max_drawdown", max_drawdown))} |' + NL
report += f'| 风险 | 年化波动率 | **{volatility:.1%}** | {stars_str(star_rating("volatility", volatility))} |' + NL
report += f'| 风险调整 | Sharpe Ratio | **{sharpe:.2f}** | {stars_str(star_rating("sharpe", sharpe))} |' + NL
report += f'| 风险调整 | Sortino Ratio | **{sortino:.2f}** | {stars_str(star_rating("sortino", sortino))} |' + NL
report += f'| 风险调整 | Calmar Ratio | **{calmar:.2f}** | {stars_str(star_rating("calmar", calmar))} |' + NL
report += f'| 交易 | 总交易对数 | **{n_trades}** | - |' + NL
report += f'| 交易 | 胜率 (Win Rate) | **{win_rate:.1%}** | {stars_str(star_rating("win_rate", win_rate))} |' + NL
report += f'| 交易 | 盈亏比 (Payoff Ratio) | **{payoff_ratio:.2f}** | {stars_str(star_rating("payoff_ratio", payoff_ratio))} |' + NL
report += f'| 交易 | Profit Factor | **{profit_factor:.2f}** | {stars_str(star_rating("profit_factor", profit_factor))} |' + NL
report += f'| 交易 | 最长连赢 | **{max_consec_wins}** 笔 | - |' + NL
report += f'| 交易 | 最长连亏 | **{max_consec_losses}** 笔 | - |' + NL
report += f'| 分布 | 偏度 (Skewness) | **{skewness:+.2f}** | {stars_str(star_rating("skewness", skewness))} |' + NL
report += f'| 分布 | 峰度 (Kurtosis) | **{kurtosis:+.2f}** | - |' + NL
report += f'| 月度 | 月度胜率 | **{monthly_win_rate:.1%}** | {stars_str(star_rating("monthly_win_rate", monthly_win_rate))} |' + NL
report += f'| 月度 | 最大单月收益 | **{max_monthly_win:+.1%}** | - |' + NL
report += f'| 月度 | 最大单月亏损 | **{max_monthly_loss:+.1%}** | - |' + NL
report += NL
report += '---' + NL + NL
report += '## 2. 市场环境对比 (vs HS300 基准)' + NL + NL
report += '| 指标 | HS300 基准 | MR v5 策略 | 评价 |' + NL
report += '|------|-----------|------------|------|' + NL
bm_eval = f'年化超额 **{annual_return-bm_annual_return:+.1%}**' if annual_return > bm_annual_return else f'跑输 **{annual_return-bm_annual_return:+.1%}**'
risk_reduction = f'风险降低 {abs((bm_vol-volatility)/bm_vol)*100:.0f}%' if bm_vol > volatility else f'风险增加 {abs((bm_vol-volatility)/bm_vol)*100:.0f}%'
dd_control = f'回撤控制 {abs((bm_max_dd-max_drawdown)/abs(bm_max_dd))*100:.0f}%' if abs(bm_max_dd) > abs(max_drawdown) else f'回撤更差'
sharpe_eval = f'从 {bm_sharpe:.2f} 提升' if sharpe > bm_sharpe else f'从 {bm_sharpe:.2f} 下降'
report += f'| 年化收益 | {bm_annual_return:+.2%} | {annual_return:+.2%} | {bm_eval} |' + NL
report += f'| 年化波动 | {bm_vol:.1%} | {volatility:.1%} | {risk_reduction} |' + NL
report += f'| 最大回撤 | {bm_max_dd:+.2%} | {max_drawdown:+.2%} | {dd_control} |' + NL
report += f'| Sharpe | {bm_sharpe:.2f} | {sharpe:.2f} | {sharpe_eval} |' + NL
report += f'| 月度胜率 | {bm_monthly_win:.1%} | {monthly_win_rate:.1%} | 稳定度{"提升" if monthly_win_rate > bm_monthly_win else "下降"} |' + NL
report += NL
report += '---' + NL + NL
report += '## 3. 年度对比' + NL + NL
report += '| 年度 | HS300 | MR v5 | 超额 | v5 胜率 | v5 笔数 |' + NL
report += '|------|-------|-------|------|---------|---------|' + NL

# Yearly trade counts and win rates
yearly_trade_counts = {}
yearly_win_rates = {}
if not trades_df.empty:
    for sym, grp in trades_df.groupby('symbol'):
        b = grp[grp['action'] == 'BUY'].sort_values('date')
        s = grp[grp['action'] == 'SELL'].sort_values('date')
        for i in range(min(len(b), len(s))):
            yr = s.iloc[i]['date'].year
            yearly_trade_counts[yr] = yearly_trade_counts.get(yr, 0) + 1
            pnl = s.iloc[i]['price'] / b.iloc[i]['price'] - 1
            if yr not in yearly_win_rates:
                yearly_win_rates[yr] = []
            yearly_win_rates[yr].append(pnl)

for yr, ret in yearly_returns:
    b = bm_yearly.get(yr, 0)
    diff = ret - b
    wr = np.mean([1 if p > 0 else 0 for p in yearly_win_rates.get(yr, [])]) if yr in yearly_win_rates else 0
    cnt = yearly_trade_counts.get(yr, 0)
    report += f'| {yr} | {float(b):+.1%} | {ret:+.1%} | {diff:+.1%} | {wr:.1%} | {cnt} |' + NL

report += NL
report += '---' + NL + NL
report += '## 4. 出场原因分析' + NL + NL
report += '| 原因 | 笔数 | 占比 | 平均收益 | 胜率 | 说明 |' + NL
report += '|------|------|------|----------|------|------|' + NL
reason_desc = {
    'corp_action': '除权退出',
    'crash': '暴跌清仓',
    'sl': '止损',
    'time': '时间止损(主力)',
    'tp': '止盈',
}
for r in exit_reason_stats:
    desc = reason_desc.get(r['reason'], r['reason'])
    report += f'| {r["reason"]} | {r["count"]} | {r["pct"]:.0f}% | {r["avg_pnl"]:+.2%} | {r["win_rate"]:.0%} | {desc} |' + NL

report += NL
report += '---' + NL + NL
report += '## 5. 收益分布特征' + NL + NL
report += '| 指标 | 数值 |' + NL
report += '|------|------|' + NL
report += f'| 平均每笔收益 | {avg_pnl:+.3%} |' + NL
report += f'| 中位数收益 | {median_pnl:+.3%} |' + NL
report += f'| 标准差 | {std_pnl:.3%} |' + NL
report += f'| 偏度 (Skewness) | {skewness:+.2f} (正偏=赚大亏小) |' + NL
report += f'| 峰度 (Kurtosis) | {kurtosis:+.2f} (尖峰=极端值较多) |' + NL
report += f'| 最大单笔盈利 | {max_win:+.1%} |' + NL
report += f'| 最大单笔亏损 | {max_loss:+.1%} |' + NL
report += f'| >5% 收益占比 | {pct_big_win:.1f}% |' + NL
report += f'| <-5% 亏损占比 | {pct_big_loss:.1f}% |' + NL
report += f'| 平均持仓天数 | {avg_hold:.1f} 天 |' + NL
report += NL
report += '---' + NL + NL
report += '## 6. 评级标准' + NL + NL
report += '| ★ | 评级 | 标准 |' + NL
report += '|----|------|------|' + NL
report += '| ★★★★★ | 世界级 | 极少策略能达到 |' + NL
report += '| ★★★★☆ | 专业级 | 量化基金核心指标 |' + NL
report += '| ★★★☆☆ | 合格 | 可接受的底线 |' + NL
report += '| ★★☆☆☆ | 偏弱 | 需改进 |' + NL
report += '| ★☆☆☆☆ | 不合格 | 应放弃 |' + NL
report += NL
report += '---' + NL + NL
report += '## 7. 实现位置' + NL + NL
report += '- 策略模块: `atos/backtest/mr_v2.py`' + NL
report += '- 聚宽脚本: `JQ/scripts/HS300_CYB50/strategy_HS300_CYB50.py`' + NL
report += '- 文档: `strategies/ATOS_MR_v2.md`' + NL

# Save report
report_dir = r'D:\claude-quant\reports\HS300_CYB50'
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, 'ATOS_MR_v5_new.md')

with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f'\nReport saved to: {report_path}')
print()
print('=== Summary ===')
print(f'Period: {actual_start} ~ {actual_end}')
print(f'Annual return: {annual_return:+.2%}')
print(f'Total return: {total_return:+.2%}')
print(f'Max drawdown: {max_drawdown:+.2%}')
print(f'Sharpe: {sharpe:.2f}')
print(f'Win rate: {win_rate:.1%}')
print(f'Trades: {n_trades}')
print(f'Payoff ratio: {payoff_ratio:.2f}')
print()
print('Yearly:')
for yr, ret in yearly_returns:
    print(f'  {yr}: {ret:+.2%}')
