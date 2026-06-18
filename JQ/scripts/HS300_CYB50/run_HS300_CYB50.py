# -*- coding: utf-8 -*-
"""
ATOS MR v5 - ALL detection + HS300+CYB50 trading entry point
Strategy body: strategy_HS300_CYB50.py (3616 lines, self-contained)

Detection pool: ALL 1339 stocks (HS300+CSI1000+CYB50)
Trading pool: HS300 + CYB_STAR_50 (352 stocks)
Backtest: 2018-01-01 ~ 2022-12-31, 1,000,000 capital, daily
Benchmark: 000300.XSHG (HS300)
Local expected: annual ~19.81%, MDD ~-16.57%, win ~49%, trades ~1968
"""
import sys
sys.path.insert(0, r'D:\claude-quant\JQ\scripts')

if __name__ == '__main__':
    print('ATOS MR v5 - HS300+CYB50 Combined Trading')
    print('  Detection pool: ALL 1339 stocks')
    print('  Trading pool: HS300 + CYB_STAR_50 (352 stocks)')
    print('  Period: 2018-01-01 ~ 2022-12-31')
    print('  Local expected: annual ~19.81%, MDD ~-17%, win rate ~49%')
    print()
    print('  For JQ platform: upload strategy_HS300_CYB50.py')
    print('  IMPORTANT: Set INITIAL CAPITAL = 1,000,000 in JQ backtest settings')
