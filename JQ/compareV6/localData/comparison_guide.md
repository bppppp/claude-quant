# Comparison Guide: Local vs JQ Results

## File Mapping

| Local File | JQ Equivalent |
|-----------|---------------|
| equity_curve.csv | JQ daily equity export |
| trades.csv | JQ trade log |
| yearly_returns.csv | JQ annual return column |
| summary.json | JQ performance summary |
| regime_stats.csv | Per-regime breakdown |
| sell_reasons.csv | Exit reason distribution |

## Key Metrics to Compare

1. **Annual Return** — should be within ±5pp (local has more friction modeled)
2. **Max Drawdown** — should be close (±2pp)
3. **Win Rate** — should be close (±3pp)
4. **Trade Count** — local may have fewer (stricter suspension checks)
5. **Yearly Returns** — compare year-by-year pattern
6. **Sell Reason Distribution** — check if exit patterns match

## Expected Differences

- Local may be slightly lower due to:
  - More conservative limit-up/down detection
  - Transfer fee (0.001%) included
  - Stricter delisting checks
  - Data source differences (复权方式)

- JQ may differ due to:
  - Different stock universe snapshots (JQ uses real-time composition)
  - Different RSI implementation (Wilder vs EMA)
  - Different suspension/pause detection

## How to Add JQ Results

1. Export JQ backtest results as CSV/JSON
2. Save to `reports/ATOS_MR_v6/jq_results/`
3. Run `python scripts/compare_v6.py` to generate comparison report
