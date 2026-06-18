# -*- coding: utf-8 -*-
"""
ATOS MR v2 - CYB_STAR_50 test set entry point
Strategy body: strategy_CYB_STAR_50.py (self-contained, can be uploaded to JQ as-is)

Backtest:
  - Period: 2018-01-01 ~ 2022-12-31
  - Capital: 1,000,000
  - Frequency: daily
  - Benchmark: 399006.XSHE (ChiNext Index)
"""
import sys
sys.path.insert(0, r'D:\claude-quant\JQ\scripts')

if __name__ == '__main__':
    print('ATOS MR v2 - CYB_STAR_50 Test Set')
    print('  Universe: CYB_STAR_50 (100 stocks after DISABLE_STOCK filter)')
    print('  Period: 2018-01-01 ~ 2022-12-31')
    print('  Local expected: annual ~22.97%, MDD ~-10%, win rate ~50%')
    print('  Local backtest: D:\claude-quant\atos\backtest\mr_v2.py')
    print()
    print('  For JQ platform: upload strategy_CYB_STAR_50.py')
