# -*- coding: utf-8 -*-
"""
ATOS MR v2 - HS300 test set entry point
Strategy body: strategy_HS300.py (self-contained, can be uploaded to JQ as-is)

Backtest:
  - Period: 2018-01-01 ~ 2022-12-31
  - Capital: 1,000,000
  - Frequency: daily
  - Benchmark: 000300.XSHG
"""
import sys
sys.path.insert(0, r'D:\claude-quant\JQ\scripts')

if __name__ == '__main__':
    print('ATOS MR v2 - HS300 Test Set')
    print('  Universe: HS300 (296 stocks after DISABLE_STOCK filter)')
    print('  Period: 2018-01-01 ~ 2022-12-31')
    print('  Local expected: annual ~26.52%, MDD ~-15%, win rate ~50%')
    print('  Local backtest: D:\claude-quant\atos\backtest\mr_v2.py')
    print()
    print('  For JQ platform: upload strategy_HS300.py')
