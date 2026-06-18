# ATOS MR v2 策略 -> 聚宽 JQ 回测脚本 生成要点

> **目的**: 把本地回测引擎 `atos/backtest/mr_v2.py` 的均值回归策略, 移植到聚宽 (JQBoson) 平台验证。
> **关联文档**: `D:\claude-quant\JQ\createBase\JQuantAPI.md`
> **策略核心**: 5 日跌幅 > 10% AND RSI(6) < 20 (主信号), BULL 副信号: 5 日跌幅 > 8% AND RSI(6) < 30

---

## 1. 策略逻辑映射 (本地 -> JQ)

| 本地 (mr_v2.py) | JQ 等价实现 | 备注 |
|------------------|--------------|------|
| `_compute_signal_v2(df)` | `history` + 自计算 | 见 3.1 |
| `detect_full_regime` + 滞后 | `history` + 自计算 + 滞后 3 天 | 见 3.2 |
| `_execute_buy_on_execution` | `run_daily` 14:50 排队, 09:30 撮合 | T+1 |
| `_execute_sell_on_execution` | `run_daily` 15:00 触发, 限价单次日 | 见 4.3 |
| 涨跌停检测 | `get_current_data()` + OHLC | 见 4.4 |
| 停牌检测 | `cd[s].paused` | JQ 内置 |
| 100 股整手 | `order(stock, shares)` + 自计算 | 见 4.5 |
| 滑点 0.1% | `set_slippage(FixedSlippage(0.002))` | 双边 0.1% |
| 佣金 0.025% + 印花税 0.1% | `set_order_cost(...)` | 见 5.1 |
| T+1 卖出 | `get_current_data()` + pending 队列 | JQ 默认 T+1 |

---

## 2. 必须注意的 JQ 引擎 quirk (避免策略失效)

### 2.1 Python 3.6 兼容 (JQBoson 不是 3.7+)

**禁止使用**:
```python
HS300_CODES: list[str] = [...]   # PEP 585
PARAMS: dict[str, int] = {...}   # PEP 585
def f() -> int | None:            # PEP 604
match x: case 1: ...              # PEP 634
```

**应使用**: 无注解。

### 2.2 ⚠️ `np.isnan(合法正数)` 在 JQ 返回 `True` (最隐蔽)

**症状**: 策略全市场无交易, 日志显示 `score=0.00`
**修复**: 用 `np.isfinite` 代替 `not np.isnan`:
```python
# 错
if any(x is None or np.isnan(x) for x in [rsi, drop_5d]):
    return 0

# 对
for v in [rsi, drop_5d]:
    if not np.isfinite(v):
        return 0
```

### 2.3 `get_current_data()` 是 lazy loading

```python
cd = get_current_data()
# 错: cd.get(s) 永远返回 None (初始为空)
# 对: cd[s] 触发加载, 用 try/except 兜底
try:
    d = cd[s]
except KeyError:
    continue
```

### 2.4 `attribute_history(skip_paused=True)` 会过度过滤

```python
# 错: 跳过停牌日 -> 多数股票历史不足 60 日
hist = attribute_history(s, 60, '1d', ['close'], skip_paused=True)

# 对: skip_paused=False + n=70 (留 buffer)
hist = attribute_history(s, 70, '1d', ['close'], skip_paused=False, df=False)
if hist is None or len(hist['close']) < 60:
    continue
recent = hist['close'][-30:]
if any(np.isnan(recent)):
    continue
```

### 2.5 科创板 (688xxx) 必须用限价单

```python
# 错: order(stock, delta) 在科创板会失败
if stock.startswith('688'):
    order(stock, delta, LimitOrderStyle(min(last_price * 1.005, 9999.99)))
else:
    order(stock, delta)
```

### 2.6 `order_target_value` 内部股数 0 假报

```python
# 错: 偶尔报"下单数量为0"
order_target_value(stock, value)

# 对: 直接传股数
target_shares = int(value // (100 * last_price)) * 100
delta = target_shares - current_shares
order(stock, delta)
```

### 2.7 `cd[stock]` 对退市/异常股票抛 KeyError

```python
# 错: 直接 cd[stock].paused 会抛 KeyError 终止策略
# 对: 用 try/except 守护
try:
    d = cd[s]
except KeyError:
    continue  # 退市/未上市
```

### 2.8 `high_limit` / `low_limit` 可能为 0 (新股首日)

```python
# 错: last_price >= cd[s].high_limit (新股恒真)
# 对: 加 > 0 守护
if cd[s].high_limit > 0 and last_price >= cd[s].high_limit:
    continue
```

---

## 3. 核心计算: 信号 + 状态

### 3.1 入场信号

```python
def compute_signals_jq(stock_list, context):
    """
    主信号: 5 日跌幅 > 10% AND RSI(6) < 20
    BULL 副信号: 5 日跌幅 > 8% AND RSI(6) < 30
    """
    n = 30
    df_close = history(n, unit='1d', field='close', security_list=stock_list,
                       df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        return {}

    signals = {}
    cd = get_current_data()
    for stock in stock_list:
        try:
            close_s = df_close[stock].dropna()
            if len(close_s) < 15:
                continue
        except KeyError:
            continue

        current_close = close_s.iloc[-1]
        prev_5_close = close_s.iloc[-6] if len(close_s) >= 6 else current_close
        drop_5d = current_close / prev_5_close - 1

        rsi6 = calc_rsi(close_s, period=6)
        if not np.isfinite(rsi6) or not np.isfinite(drop_5d):
            continue

        if drop_5d < -0.10 and rsi6 < 20:
            signals[stock] = ('main', rsi6)
        elif drop_5d < -0.08 and rsi6 < 30:
            if g.regime == 'BULL':
                signals[stock] = ('secondary', rsi6)

    return signals


def calc_rsi(close, period=6):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if not np.isfinite(avg_gain) or not np.isfinite(avg_loss):
        return np.nan
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
```

### 3.2 状态识别 (滞后 3 天避免前视)

```python
def detect_regime_jq(context):
    market = '000300.XSHG'
    h = attribute_history(market, 250, '1d',
                          ['close', 'high', 'low'], df=True, fq='pre')
    if h is None or h.empty:
        return 'SIDEWAYS'

    close = h['close']
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    if len(close) < 63:
        return 'SIDEWAYS'
    c_t3 = close.iloc[-4]  # T-3 数据, 避免前视
    ma20_t3 = ma20.iloc[-4]
    ma60_t3 = ma60.iloc[-4]
    slope_ma20 = (ma20.iloc[-4] - ma20.iloc[-23]) / 19

    if not all(np.isfinite([c_t3, ma20_t3, ma60_t3, slope_ma20])):
        return 'SIDEWAYS'

    crash_5d = c_t3 / close.iloc[-8] - 1 if len(close) >= 8 else 0
    crash_20d = c_t3 / close.iloc[-23] - 1 if len(close) >= 23 else 0
    if crash_5d <= -0.08 or crash_20d <= -0.15:
        return 'CRASH'

    if ma20_t3 > ma60_t3 and c_t3 > ma20_t3 and slope_ma20 > 0:
        return 'BULL'

    if ma20_t3 < ma60_t3:
        return 'BEAR'

    return 'SIDEWAYS'
```

---

## 4. 交易执行

### 4.1 初始化

```python
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_tax=0, close_tax=0.001,
        open_commission=0.00025, close_commission=0.00025,
        close_today_commission=0, min_commission=5
    ), type='stock')
    set_slippage(FixedSlippage(0.002))
    set_universe(HS300_CODES_JQ)  # 预填 cd

    g.holdings = {}
    g.pending_buys = []
    g.pending_sells = []
    g.MAX_PENDING_DAYS = 20
    g.regime = 'SIDEWAYS'

    run_daily(before_market_open, '09:00')
    run_daily(execute_pending_orders, '09:30')
    run_daily(check_exit_signals, '14:50')


def before_market_open(context):
    g.regime = detect_regime_jq(context)


# 6 位代码 -> JQ 代码 (6 开头 .XSHG, 其他 .XSHE)
HS300_CODES_JQ = [
    (c + '.XSHG' if c.startswith('6') else c + '.XSHE')
    for c in HS300_CODES_RAW  # 从本地 data/config.py 复制
]
```

### 4.2 T 日 14:50 决策

```python
def check_exit_signals(context):
    portfolio = context.portfolio
    cd = get_current_data()
    cash = portfolio.available_cash
    total_value = portfolio.total_value

    g.regime = detect_regime_jq(context)
    regime_mult = {'BULL': 1.5, 'SIDEWAYS': 1.0, 'BEAR': 0.2,
                   'CHOPPY_BEAR': 0.3, 'CRASH': 0.0}.get(g.regime, 0.5)

    raw_universe = list(g.holdings.keys()) + [s for s, _, _ in g.pending_buys]
    available = [s for s in HS300_CODES_JQ if s not in raw_universe]
    signals = compute_signals_jq(available, context)

    position_pct = 0.15
    max_positions = 20
    n_to_buy = max_positions - len(g.holdings) - len(g.pending_buys)
    if g.regime != 'CRASH' and n_to_buy > 0:
        sorted_signals = sorted(signals.items(), key=lambda x: x[1][1])
        for stock, (sig_type, rsi) in sorted_signals[:n_to_buy]:
            try:
                d = cd[stock]
            except KeyError:
                continue
            if d.paused: continue
            if d.is_st: continue
            if d.high_limit > 0 and d.last_price >= d.high_limit: continue
            try:
                h = attribute_history(stock, 10, '1d', ['pct_change'],
                                       skip_paused=False, df=False, fq='pre')
                if h is not None:
                    recent_pct = [x for x in h['pct_change']
                                  if x is not None and not np.isnan(x)]
                    if any(abs(x) > 15.0 for x in recent_pct[-5:]):
                        continue
            except Exception:
                pass
            g.pending_buys.append((stock, context.current_dt.date(),
                                    float(d.last_price)))

    cur_tp = 0.30
    cur_sl = -0.05
    cur_hold = 10
    for stock, pos in list(g.holdings.items()):
        if pos['entry_date'] == context.current_dt.date():
            try:
                d = cd[stock]
                pos['last_close'] = float(d.last_price) if d.last_price > 0 else pos['entry_price']
            except KeyError:
                pos['last_close'] = pos['entry_price']
            continue

        try:
            d = cd[stock]
        except KeyError:
            continue
        cur_close = float(d.last_price)
        if cur_close <= 0: continue
        ret = (cur_close - pos['entry_price']) / pos['entry_price']
        days_held = np.busday_count(pos['entry_date'], context.current_dt.date())

        is_corp = False
        try:
            h = attribute_history(stock, 1, '1d', ['pct_change'],
                                   skip_paused=False, df=False, fq='pre')
            if h is not None and len(h['pct_change']) > 0:
                today_pct = h['pct_change'][-1]
                if today_pct is not None and not np.isnan(today_pct):
                    is_corp = abs(today_pct) > 15.0
        except Exception:
            pass

        should_sell = False
        reason = ''
        if is_corp:
            should_sell = True; reason = 'corp_action'
        elif ret >= cur_tp:
            should_sell = True; reason = 'tp'
        elif ret <= cur_sl:
            should_sell = True; reason = 'sl'
        elif days_held >= cur_hold:
            should_sell = True; reason = 'time'
        elif g.regime == 'CRASH':
            should_sell = True; reason = 'crash'

        if should_sell:
            if not any(p[0] == stock for p in g.pending_sells):
                g.pending_sells.append((stock, 1.0, reason, context.current_dt.date()))

    log.info("[%s] regime=%s, holdings=%d, pending_buys=%d, pending_sells=%d, signals=%d"
             % (context.current_dt.date(), g.regime, len(g.holdings),
                len(g.pending_buys), len(g.pending_sells), len(signals)))
```

### 4.3 T+1 09:30 撮合

```python
def execute_pending_orders(context):
    portfolio = context.portfolio
    cd = get_current_data()
    today = context.current_dt.date()
    cash = portfolio.available_cash
    total_value = portfolio.total_value

    # 1. pending_sells
    new_pending_sells = []
    for stock, ratio, reason, queue_date in g.pending_sells:
        if stock not in g.holdings:
            continue
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused: continue
        if d.low_limit > 0 and d.last_price <= d.low_limit:
            days_pending = (today - queue_date).days
            if days_pending < g.MAX_PENDING_DAYS:
                new_pending_sells.append((stock, ratio, reason, queue_date))
                continue
            else:
                exec_price = float(d.day_open) * 0.95
        else:
            exec_price = float(d.day_open)

        pos = g.holdings[stock]
        if reason == 'corp_action':
            try:
                h = attribute_history(stock, 2, '1d', ['close'],
                                       skip_paused=False, df=False, fq='pre')
                if h is not None and len(h['close']) >= 2:
                    exec_price = float(h['close'][-2])
            except Exception:
                pass

        sell_shares = pos['shares']
        if stock.startswith('688'):
            limit_price = min(exec_price * 0.995, 9999.99)
            order(stock, -sell_shares, LimitOrderStyle(limit_price))
        else:
            order(stock, -sell_shares)
        del g.holdings[stock]
    g.pending_sells = new_pending_sells

    # 2. pending_buys
    new_pending_buys = []
    regime_mult = {'BULL': 1.5, 'SIDEWAYS': 1.0, 'BEAR': 0.2,
                   'CHOPPY_BEAR': 0.3, 'CRASH': 0.0}.get(g.regime, 0.5)
    for stock, sig_date, sig_close in g.pending_buys:
        if stock in g.holdings:
            continue
        try:
            d = cd[stock]
        except KeyError:
            continue
        if d.paused: continue
        if d.high_limit > 0 and d.last_price >= d.high_limit: continue
        per_value = total_value * 0.15 * regime_mult
        last_price = float(d.day_open)
        if last_price <= 0 or not np.isfinite(last_price): continue
        shares = int(per_value / (last_price * 1.001) / 100) * 100
        if shares < 100: continue
        cost = shares * last_price * 1.001
        if cost > cash * 0.95:
            affordable = int(cash * 0.95 / (last_price * 1.001) / 100) * 100
            if affordable < 100: continue
            shares = affordable
        if stock.startswith('688'):
            limit_price = min(last_price * 1.005, 9999.99)
            order(stock, shares, LimitOrderStyle(limit_price))
        else:
            order(stock, shares)
        g.holdings[stock] = {
            'entry_date': today,
            'entry_price': last_price,
            'shares': shares,
            'last_close': last_price,
        }
    g.pending_buys = new_pending_buys
```

### 4.4 涨跌停/停牌综合过滤

```python
def check_filters(stock, cd):
    try:
        d = cd[stock]
    except KeyError:
        return False, 'delisted'
    if d.paused: return False, 'paused'
    if d.is_st: return False, 'st'
    if d.high_limit > 0 and d.last_price >= d.high_limit: return False, 'limit_up'
    if d.low_limit > 0 and d.last_price <= d.low_limit: return False, 'limit_down'
    if d.last_price <= 0 or not np.isfinite(d.last_price): return False, 'invalid_price'
    return True, ''
```

### 4.5 100 股整手

```python
def calc_shares(value, price, lot_size=100):
    if price <= 0 or not np.isfinite(price):
        return 0
    cost_per_share = price * 1.001  # 滑点 0.1%
    shares = int(value / cost_per_share / lot_size) * lot_size
    return max(shares, 0)
```

---

## 5. 完整骨架

### 5.1 成本与滑点对照

| 项 | 本地 (mr_v2.py) | JQ 等价 |
|---|---|---|
| 佣金 | 0.025% (min 5) | open_commission=0.00025, min_commission=5 |
| 印花税 | 0.1% (卖出) | close_tax=0.001 |
| 过户费 | 0.001% | JQ 默认 0 |
| 滑点 | 0.1% 单边 | FixedSlippage(0.002) (双边 0.1%) |

### 5.2 聚宽平台运行步骤

1. 登录聚宽: https://www.joinquant.com
2. 新建策略 -> Python3 (JQBoson)
3. 粘贴代码
4. 设置回测区间: 2018-01-01 ~ 2022-12-31, 1,000,000, 日
5. 运行回测
6. 对比本地 26.52% 年化, 允许 1-3pp 误差, > 5pp 差异检查 §2 的 quirk

---

## 6. 验证清单

| # | 验证项 | 期望 |
|---|--------|------|
| 1 | 策略无报错运行 | 5 年回测完成 |
| 2 | 总交易笔数 | ~1700-1900 (本地 1772) |
| 3 | 年化收益 | 25-30% (本地 26.52%) |
| 4 | 最大回撤 | -15% 左右 |
| 5 | 年度收益 | 4/5 年跑赢基准 |
| 6 | T+1 违规 | 0 |
| 7 | 涨停日买入 | 0 |
| 8 | 跌停日卖出 | 0 |
| 9 | 停牌日交易 | 0 |
| 10 | ST/退市交易 | 0 |
| 11 | 100 股整手 | 100% |

**关键诊断日志**:
```python
log.info("[%s] regime=%s, holdings=%d, pending_buys=%d, pending_sells=%d, signals=%d"
         % (context.current_dt.date(), g.regime, len(g.holdings),
            len(g.pending_buys), len(g.pending_sells), len(signals)))
```

**0 笔交易诊断** (按 JQuantAPI.md §17.5 checklist):
1. cd.get(s) -> 改 cd[s] + try/except
2. np.isnan(正数) -> 改 np.isfinite
3. attribute_history(skip_paused=True) -> 改 skip_paused=False + n=70
4. 信号返回 0 -> 检查 np.isnan 误判
5. 持仓一直为 0 -> 检查 pending_buys T+1 撮合

---

## 7. 与本地回测的差异预期

| 差异源 | 预期偏差 |
|--------|----------|
| JQ FixedSlippage(0.002) vs 本地 0.1% | +/-1% |
| JQ 撮合规则 (市价/限价) | +/-2% |
| 复权方式 (JQ 前复权) | +/-0.5% |
| position.avg_cost | +/-1% |
| 涨跌停价 (交易所 vs 手工) | +/-0.3% |
| **总预期偏差** | **+/-3-5%** |

如果差异 > 5%, 大概率是 §2 的 quirk 没处理好。

---

## 8. FAQ

**Q1: 聚宽无交易但本地有?**
A: 99% 是 §2.2 (np.isnan) 或 §2.3 (cd.get) 问题。

**Q2: 收益差异大?**
A: 检查 §2.1 (PEP 585), §2.5 (科创板), §2.6 (order_target_value)。

**Q3: 复权不一致?**
A: 用 use_real_price=True + fq='pre'。

**Q4: 获取当前价?**
A: cd[stock].last_price (09:30 后)。

**Q5: T+1 实现?**
A: JQ 默认 T+1, 用 pending 队列模拟 T 日决策 + T+1 09:30 撮合。

**Q6: 调试?**
A: log.info() 输出到日志, record() 保存到收益图。

---

## 9. 参考资料

- D:\claude-quant\JQ\createBase\JQuantAPI.md
- D:\claude-quant\atos\backtest\mr_v2.py
- D:\claude-quant\strategies\ATOS_MR_v2.md
- D:\claude-quant\reports\ATOS_MR_v2_HS300_report.md
