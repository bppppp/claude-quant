# -*- coding: utf-8 -*-
"""
ATOS MR v2 - CSI1000 test set entry point
Strategy body: strategy_CSI1000.py (self-contained, can be uploaded to JQ as-is)

Backtest:
  - Period: 2018-01-01 ~ 2022-12-31
  - Capital: 1,000,000
  - Frequency: daily
  - Benchmark: 000300.XSHG
"""
import sys
sys.path.insert(0, r'D:\claude-quant\JQ\scripts')

if __name__ == '__main__':
    print('ATOS MR v2 - CSI1000 Test Set')
    print('  Universe: CSI1000 (988 stocks after DISABLE_STOCK filter)')
    print('  Period: 2018-01-01 ~ 2022-12-31')
    print('  Local expected: annual ~9.67%, MDD ~-38%, win rate ~43%')
    print('  Local backtest: D:\claude-quant\atos\backtest\mr_v2.py')
    print()
    print('  For JQ platform: upload strategy_CSI1000.py')
