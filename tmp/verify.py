"""Verify with different universes and periods"""
import sys
sys.path.insert(0, 'D:/claude-quant')
from atos.backtest.mr_v2 import backtest_v2

# Test 1: Different universes
print('=== Test 1: Different universes (2018-2022) ===')
for uni in ['HS300', 'CSI1000', 'CYB_STAR_50']:
    try:
        r = backtest_v2('2018-01-01', '2022-12-31', uni, verbose=False)
        print(f"  {uni:<15} ann={r['annual_return']*100:>+6.2f}% tot={r['total_return']*100:>+6.2f}% mdd={r['max_drawdown']*100:>+6.2f}% trades={r['n_trades']}")
    except Exception as e:
        print(f"  {uni}: ERROR {e}")

# Test 2: Different time periods
print()
print('=== Test 2: HS300 different periods ===')
periods = [
    ('2018-01-01', '2018-12-31', '2018 only (bear)'),
    ('2019-01-01', '2019-12-31', '2019 only (bull)'),
    ('2020-01-01', '2020-12-31', '2020 only (bull+COVID)'),
    ('2021-01-01', '2021-12-31', '2021 only (sideways)'),
    ('2022-01-01', '2022-12-31', '2022 only (bear)'),
    ('2018-01-01', '2019-12-31', '2018-2019'),
    ('2020-01-01', '2022-12-31', '2020-2022'),
]
for start, end, name in periods:
    try:
        r = backtest_v2(start, end, 'HS300', verbose=False)
        print(f"  {name:<25} ann={r['annual_return']*100:>+6.2f}% tot={r['total_return']*100:>+6.2f}% mdd={r['max_drawdown']*100:>+6.2f}% trades={r['n_trades']}")
    except Exception as e:
        print(f"  {name}: ERROR {e}")
