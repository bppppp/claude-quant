# -*- coding: utf-8 -*-
"""
ATOS MR v2 - Local batch backtest (matches JQ platform scripts)

Run all 4 test sets: HS300, CSI1000, CYB_STAR_50, ALL (combined)

Run: PYTHONPATH=. python JQ/scripts/run_all.py
"""
import sys
import os
sys.path.insert(0, r'D:\claude-quant')

import time
from atos.backtest.mr_v2 import backtest_v2


def run_one(name, start='2018-01-01', end='2022-12-31'):
    print('=' * 70)
    print('Test set: ' + name)
    print('Period:  ' + start + ' ~ ' + end)
    print('=' * 70)
    t0 = time.time()
    result = backtest_v2(start, end, name, verbose=False)
    elapsed = time.time() - t0

    print('Annual:    %+.2f%%' % (result['annual_return'] * 100))
    print('Total:     %+.2f%%' % (result['total_return'] * 100))
    print('Max DD:    %.2f%%' % (result['max_drawdown'] * 100))
    print('Trades:    %d' % result['n_trades'])
    print('Win rate:  %.1f%%' % (result['win_rate'] * 100))
    print('Final:     %.0f' % result['final_equity'])
    print('Time:      %.1fs' % elapsed)
    print()
    print('Yearly:')
    for y, r in result['yearly_returns']:
        print('  %d: %+.2f%%' % (y, r * 100))
    print()
    return result


if __name__ == '__main__':
    print('ATOS MR v2 - Batch Backtest')
    print('Same test sets as JQ platform scripts (4 universes)')
    print('Each test set has its own folder under JQ/scripts/')
    print()
    test_sets = ['HS300', 'CSI1000', 'CYB_STAR_50', 'ALL']
    results = {}
    for name in test_sets:
        results[name] = run_one(name)
    print('=' * 70)
    print('Summary')
    print('=' * 70)
    print('%-15s %10s %10s %10s' % ('Universe', 'Annual', 'Total', 'MaxDD'))
    for name in test_sets:
        r = results[name]
        print('%-15s %+9.2f%% %+9.2f%% %9.2f%%' % (
            name, r['annual_return'] * 100, r['total_return'] * 100, r['max_drawdown'] * 100))
