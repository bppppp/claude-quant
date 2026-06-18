# JQuant API Reference — 聚宽量化平台

> Python3.6 环境 · `♠` = 仅回测/模拟可用 · 价格=元 · 时间=北京时间 UTC+8 · 成交量=股

---

## 快速索引

| 分类 | 核心函数 | 用途 |
|------|----------|------|
| [策略架构](#1-策略架构) | `initialize` `handle_data` `run_daily` `before_trading_start` `after_trading_end` | 生命周期 & 定时 |
| [策略设置](#2-策略设置) | `set_benchmark` `set_order_cost` `set_slippage` `set_option` | 回测参数配置 |
| [行情数据](#3-行情数据) | `get_price` `history` `attribute_history` `get_bars` `get_current_data` | K线 & 实时数据 |
| [Tick数据](#4-tick数据) | `get_current_tick` `get_ticks` `get_call_auction` | Tick级 & 集合竞价 |
| [财务数据](#5-财务数据) | `get_fundamentals` `get_fundamentals_continuously` `get_history_fundamentals` `get_valuation` | 财报 & 市值 |
| [标的信息](#6-标的信息) | `get_all_securities` `get_index_stocks` `get_industry_stocks` `get_industry` | 股票池 & 行业 |
| [因子&库](#7-因子库) | `get_factor_values` `alpha101` `alpha191` `technical_analysis` | 因子 & 技术指标 |
| [交易下单](#8-交易下单) | `order` `order_target` `order_value` `order_target_value` `cancel_order` `get_open_orders` `get_trades` | 委托 & 订单管理 |
| [组合优化](#9-组合优化) | `portfolio_optimizer` + targets/constraints/bounds | 权重优化 |
| [数据处理](#10-数据处理) | `neutralize` `winsorize` `winsorize_med` `standardlize` | 因子处理 |
| [对象](#11-对象) | `context` `portfolio` `Position` `Order` `Trade` `Tick` | 数据对象属性 |
| [Tick策略](#12-tick策略) | `handle_tick` `subscribe` `unsubscribe` `unsubscribe_all` | Tick级策略 |
| [分仓/期货/两融](#13-分仓期货两融) | `set_subportfolios` `transfer_cash` `get_dominant_future` `margincash_*` | 多账户 & 衍生品 |
| [工具函数](#14-工具函数) | `record` `log` `write_file` `read_file` `create_backtest` `get_backtest` | 日志 & IO |
| [关键规则](#15-关键规则) | 撮合/复权/停牌/限制/时间线 | 避坑速查 |
| [常见坑点](#16-常见坑点--jqboson-引擎兼容性-quirks) | `sum(dict_values)` / `order_value` 语义 / 退市保护 / 模拟盘交易日 | 兼容性 Quirks |

---

## 0. 最小可用策略

```python
import jqdata

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)   # 强烈建议开启，避免未来函数
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003,
                   close_commission=0.0003, close_today_commission=0, min_commission=5),
                   type='stock')          # 默认佣金万3 + 最低5元 + 卖出千1印花税
    g.security = '000001.XSHE'
    run_daily(market_open, time='every_bar')

def market_open(context):
    close_data = attribute_history(g.security, 5, '1d', ['close'])
    MA5 = close_data['close'].mean()
    current_price = close_data['close'][-1]
    cash = context.portfolio.available_cash
    pos = context.portfolio.positions[g.security].closeable_amount

    if current_price > 1.01 * MA5:
        order_value(g.security, cash)     # 全仓买入
    elif current_price < MA5 and pos > 0:
        order_target(g.security, 0)       # 全仓卖出
    record(stock_price=current_price)
```

### 0.1 完整生命周期示例 (含 before/after 回调)

```python
# 导入函数库
from jqdata import *

# 初始化函数，设定基准等等
def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    # log.set_level('order', 'error')

    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')

    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG')
      # 开盘时运行
    run_daily(market_open, time='open', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')

## 开盘前运行函数
def before_market_open(context):
    # 输出运行时间
    log.info('函数运行时间(before_market_open)：'+str(context.current_dt.time()))

    # 给微信发送消息（添加模拟交易，并绑定微信生效）
    # send_message('美好的一天~')

    # 要操作的股票：平安银行（g.为全局变量）
    g.security = '000001.XSHE'

## 开盘时运行函数
def market_open(context):
    log.info('函数运行时间(market_open):'+str(context.current_dt.time()))
    security = g.security
    # 获取股票的收盘价
    close_data = get_bars(security, count=5, unit='1d', fields=['close'])
    # 取得过去五天的平均价格
    MA5 = close_data['close'].mean()
    # 取得上一时间点价格
    current_price = close_data['close'][-1]
    # 取得当前的现金
    cash = context.portfolio.available_cash

    # 如果上一时间点价格高出五天平均价1%, 则全仓买入
    if (current_price > 1.01*MA5) and (cash > 0):
        # 记录这次买入
        log.info("价格高于均价 1%%, 买入 %s" % (security))
        # 用所有 cash 买入股票
        order_value(security, cash)
    # 如果上一时间点价格低于五天平均价, 则空仓卖出
    elif current_price < MA5 and context.portfolio.positions[security].closeable_amount > 0:
        # 记录这次卖出
        log.info('价格低于均价, 卖出 %s' % (security))
        # 卖出所有股票,使这只股票的最终持有量为0
        order_target(security, 0)

## 收盘后运行函数
def after_market_close(context):
    log.info(str('函数运行时间(after_market_close):'+str(context.current_dt.time())))
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('##############################################################')
```

---

## 1. 策略架构

### 生命周期回调

**`initialize(context)`**

全局只执行一次（回测开始 / 模拟盘第一次启动）。用于：设置基准、费率、全局变量 `g`。

> ⚠️ 模拟盘过程中修改代码后 initialize **不会重新执行**，需在 `after_code_changed` 中修改 `g` 变量。

**`before_trading_start(context)`**

每天 09:00 执行一次。适合放置每日初始化（如当天股票池、昨日收盘价），避免在 `handle_data` 中重复获取。

**`handle_data(context, data)`**

- 日频：每天 9:30 执行一次（实际在 9:27~9:30 之间运行），`data` 为**前一天**的日线数据
- 分钟频：每分钟第一秒执行，每天 240 次（不含 11:30 和 15:00 这两分钟），`data` 为**上一分钟**的分钟数据
- Tick 频率**不支持**此函数

`data` 是 `dict(股票代码 → SecurityUnitData)`。**按需获取**，首次访问 `data[security]` 时才加载数据。不可将 `data` 缓存到下一周期使用。

> ⚠️ 建议优先使用 `run_daily(func, time='every_bar')` 替代 `handle_data`，两者不要混用。

**`after_trading_end(context)`**

每天 15:30 执行。此时当天所有未完成订单已自动撤销。

**`on_strategy_end(context)`**

回测/模拟**正常结束**时调用（失败/手动关闭不触发）。

**`process_initialize(context)`**

- 在 `initialize` 之后执行
- 模拟盘**每天重启时都会执行**，回测只执行一次
- 用于初始化不能被 pickle 序列化的对象（如 `query(valuation)`、文件句柄、网络连接）

```python
def process_initialize(context):
    g.__query = query(valuation)  # '__' 前缀避免被 pickle 序列化
```

**`after_code_changed(context)`**

模拟盘发现代码已修改时调用（在 `process_initialize` 之前执行），用来更新旧代码中保存的 `g` 变量。

**`on_event(context, event)`**

持仓标的发生事件时触发，用 `isinstance(event, DividendsEvent)` 判断类型：
- `DividendsEvent`：分红送股（属性: `security`, `side`, `pindex`, `dividends` 列表）
- `ForcedLiquidationEvent`：强行平仓（属性: `security`, `side`, `amount`）

### 定时运行

```python
run_daily(func, time='9:30', reference_security='000001.XSHG')
```
**`time`**：
- `'HH:MM'` — 指定具体时间（精确到秒），此时**不可设** `reference_security`
- `'every_bar'` — 按策略频率运行（仅 `run_daily` 支持，Tick 频率不可用）
- `'open'` / `'open+5m'` / `'open-10m'` — 以 `reference_security` 开盘时间为基准（期货夜盘不同开盘时间），必须设 `reference_security`

**`reference_security`**：时间参照标的。`'000001.XSHG'` → 9:30-15:00。期货建议设主力合约。

> ⚠️ `func` 必须是**全局函数**（不能是类成员函数），只能接收一个 `context` 参数（不再传入 `data`，需用 `history` 等自行获取）。

```python
run_weekly(func, weekday, time='9:30', reference_security='000001.XSHG', force=False)
# weekday: 第几个交易日（负=倒数）
# force=False: 若注册晚于首次执行则不补跑；force=True: 就近补跑一次

run_monthly(func, monthday, time='9:30', reference_security='000001.XSHG', force=False)
# monthday: 第几个交易日（负=倒数）
# 首月从策略运行当天开始算：如3月20号运行，3月20号就是该月第1个交易日

unschedule_all()  # 取消所有定时任务，然后可重新注册
```

**执行顺序**：同时间点 `run_monthly > run_weekly > run_daily > before_trading_start > handle_data > after_trading_end`

**执行时间线**（股票）：
```
09:00  → run_xxx(time='09:00') → before_trading_start
09:30  → run_xxx(time='every_bar') → handle_data (日频)
09:31  → handle_data 每分钟第一秒（不含 11:30）
11:30  → 休市，不执行
13:00  → 恢复（分钟数据仍以 13:01 开始）
15:00  → 收盘，最后一根分钟 K线时间
15:30  → run_xxx(time='15:30') → after_trading_end
```

---

## 2. 策略设置

```python
set_benchmark(security)
# security: str 代码 或 dict(代码→权重), 权重和≤1
# 例: set_benchmark('600000.XSHG')
# 例: set_benchmark({'000001.XSHE':0.5,'000300.XSHG':0.3,'600000.XSHG':0.2})
# 期货想无基准: set_benchmark({"000001.XSHG":0})
```

```python
set_order_cost(OrderCost(
    open_tax=0,              # 买入印花税
    close_tax=0.001,          # 卖出印花税(股票默认千1)
    open_commission=0.0003,   # 买入佣金(股票默认万3)
    close_commission=0.0003,  # 卖出佣金(股票默认万3)
    close_today_commission=0, # 平今仓佣金(期货)
    min_commission=5          # 最低佣金(不含印花税)
), type='stock', ref=None)
# type: 'stock'|'fund'|'mmf'|'fja'|'fjb'|'fjm'|'index_futures'|'futures'|'bond_fund'|'stock_fund'|'QDII_fund'|'mixture_fund'
# ref: 为None=指定type全局生效; 为'000001.XSHE'/期货品种'AU'/期货合约'IF1709'=单独指定
# 注: 期货交割日平仓不收手续费
```

```python
set_slippage(slippage_object, type=None, ref=None)
# FixedSlippage(0.02)            — 固定值, 买卖各±0.01元
# PriceRelatedSlippage(0.002)    — 百分比, 买卖各±价格的0.1%
# StepRelatedSlippage(2)         — 期货跳数(双边), 如2跳单边1跳
# 默认滑点: PriceRelatedSlippage(0.00246)
# mmf/money_market_fund 滑点始终为0, set_slippage不生效

# 示例:
set_slippage(FixedSlippage(0.02))                                   # 全局
set_slippage(PriceRelatedSlippage(0.00246), type='stock')           # 股票
set_slippage(StepRelatedSlippage(2), type='futures', ref='CU')     # CU品种
```

```python
set_option(name, value)
# 关键选项:
#   'use_real_price': True/False     ✅强烈建议True, 动态复权避免未来函数(期货不生效)
#   'order_volume_ratio': 0.25      市价单成交量≤当日总量×value, 限价单每价成交量×value
#   'match_with_order_book': True   盘口撮合(仅模拟盘), 默认False用Bar撮合
#   't0_mode': True                 T+0实验模式(买入后可立即卖出)
#   'always_match_market_order': True  非交易时间也可下市价单立即撮合
#   'match_by_signal': True          强制撮合(限价单), 不检查价格和成交量
#   'avoid_future_data': True        开启后获取未来数据会抛FutureDataError
# 必须在 initialize 中调用

set_universe(security_list)
# 设定 history() 默认的 security_list。例: set_universe(['000001.XSHE', '600000.XSHG'])

disable_cache()
# 关闭缓存降低内存, 但运行速度明显下降, 在 initialize 中调用
```

---

## 3. 行情数据

### get_price — 多标的多字段，返回 DataFrame/Panel

```python
get_price(security, start_date=None, end_date=None, frequency='daily',
          fields=None, skip_paused=False, fq='pre', count=None, panel=True, fill_paused=True)
```
| 参数 | 说明 |
|------|------|
| `security` | str(单标的) 或 list(多标的) |
| `count` | 取`end_date`往前 N 个 `frequency` 的数据，与`start_date`互斥 |
| `start_date` | str/datetime/datetime.date。分钟数据精确到分钟 `'2015-01-01 10:00:00'` |
| `end_date` | 包含此日期。分钟数据只传日期时日内为 `00:00:00`（不含当天） |
| `frequency` | `'daily'`=`'1d'`, `'minute'`=`'1m'`, `'Xd'`(X天), `'Xm'`(X分钟, `X>1`仅支持标准OHLCVM字段) |
| `fields` | None=全部OHLCVM。支持: `open,close,high,low,volume,money,factor,high_limit,low_limit,avg,pre_close,paused,open_interest` |
| `fq` | `'pre'`(前复权,默认) / `None`(不复权) / `'post'`(后复权)。对股票/基金价格+成交量+factor生效 |
| `skip_paused` | True=跳过停牌日。panel=True多标的不支持跳过(索引需对齐) |
| `fill_paused` | True=NAN填充停牌数据, False=用pre_close填充 |
| `panel` | 建议设为False(pandas 0.25+已移除panel) |

**返回**：单标的 `DataFrame(index=datetime, columns=fields)`；多标的 panel=True→`Panel`, panel=False→`DataFrame`

```python
# 示例
df = get_price('000001.XSHE', start_date='2015-01-01', end_date='2015-01-31', frequency='1m', fields=['open', 'close'])
df = get_price('000001.XSHE', count=2, end_date='2015-01-31', frequency='daily', fields=['open', 'close'])
# 多标的
panel = get_price(get_index_stocks('000903.XSHG'))   # 中证100所有成分股
panel['open']['000001.XSHE']
```

### history — 多标的单字段 ♠

```python
history(count, unit='1d', field='avg', security_list=None,
        df=True, skip_paused=False, fq='pre')
```
- `security_list=None`：取 `set_universe()` 设定的股票池
- `field` 只支持**单字段**：`open,close,low,high,volume,money,factor,high_limit,low_limit,avg,pre_close,paused`
- `unit='Xd'/'Xm'`, X>1 时 field 仅支持 OHLCVM 标准字段
- 默认**不跳过停牌**（`skip_paused=False`），停牌用停牌前数据填充（paused 属性标识）
- `df=True` → `DataFrame(index=datetime, columns=股票代码)`
- `df=False` → `dict(代码 → numpy.array)`（对回测速度有明显提升）
- ⚠️ 不含当天的数据（收盘后也不含）

```python
h = history(5, security_list=['000001.XSHE', '000002.XSHE'])
h['000001.XSHE'][-1]     # 昨天平均价
h.iloc[-1]['000001.XSHE'] # 同上
h.mean()                   # 每列均值
```

### attribute_history — 单标的多字段 ♠

```python
attribute_history(security, count, unit='1d',
    fields=['open','close','high','low','volume','money'],
    skip_paused=True, df=True, fq='pre')
```
- 默认**跳过停牌日**（`skip_paused=True`）
- `fields` 可指定多个字段
- ⚠️ 不含当天数据

```python
h = attribute_history('000001.XSHE', 5, '1d', ('open','close','volume','factor'))
h['open']                  # Series(index=datetime)
h['close'][-1]             # 昨天收盘价
h.iloc[-1]['open']         # 昨天开盘价
h = h[h['volume'] > 1000000]     # 过滤
h['open'] = h['open'] / h['factor']  # 还原原始价格
```

### get_bars — Bar数据（含快照，不跳过停牌）

```python
get_bars(security, count, unit='1d',
    fields=['date','open','high','low','close'],
    include_now=False, end_dt=None, fq_ref_date=None, df=False)
```
- `unit`: `'1m'/'5m'/'15m'/'30m'/'60m'/'120m'/'1d'/'1w'/'1M'`，或自定义分钟 `'Xm'`(X<240)
- `include_now=True`：包含当前未完成 bar（如 9:33 取 5m bar 包含 9:30-9:33）
- `fq_ref_date`：`None`=不复权；`datetime.date.today()`=前复权；`context.current_dt`=动态复权
  - 回测中默认 `context.current_dt.date()`
  - 研究模块默认 `datetime.date.today()`
- 返回：`df=False`→`numpy.ndarray`(单标的) 或 `dict`(多标的)；`df=True`→`DataFrame`

```python
array = get_bars('000001.XSHG', 5, unit='1d', fields=['open','close'], include_now=False)
array['close']  # ndarray 以字段名索引

# 不复权:
get_bars('600507.XSHG', 5, unit='1d', fq_ref_date=None, end_dt='2018-01-05')
# 定点前复权:
get_bars('600507.XSHG', 5, unit='1d', fq_ref_date=datetime.date(2018,1,5), end_dt='2018-01-05')
```

### get_current_data — 当天实时数据 ♠

```python
get_current_data()
# 返回 dict(代码→对象), 按需获取(初始为空, 访问时加载)
# 对象属性:
#   last_price: 最新价(09:30前=昨日收盘价)
#   high_limit: 涨停价
#   low_limit: 跌停价
#   paused: 是否停牌(停牌/未上市/退市→True)
#   is_st: 是否ST(包括ST和*ST)
#   day_open: 当天开盘价(至少09:27后可获取)
#   name: 股票名称
#   industry_code: 所属行业代码(聚宽行业)
# ⚠️ 只在交易时段可用; 结果只在当天有效, 不要跨日期缓存
```

---

## 4. Tick数据

### get_current_tick ♠

```python
get_current_tick(security, dt=None, df=False)
# security: 支持股票/场内基金/期货(具体合约代码,不支持主力和指数合约)/代码列表
# dt: 指定时刻, 返回离此时刻最近的一条 tick
# 返回: 单标的→Tick对象; 列表→dict(代码→Tick); df=True→DataFrame
# 当天截至时刻未产生tick时返回None
```

### get_ticks

```python
get_ticks(security, end_dt, start_dt=None, count=None,
    fields=['time','current','high','low','volume','money'], skip=True, df=False)
# start_dt / count 二选一
# skip=True: 过滤无成交变化的tick(只保留有成交的)
# skip=False: 保留无成交但有盘口变化的tick(股票2013年起/期货2019.8.19起)
```
**返回字段**：
- 股票: `time, current, open, high, low, volume, money, a1_v~a5_v, a1_p~a5_p, b1_v~b5_v, b1_p~b5_p`
- 期货: `time, current, open, high, low, volume, money, position, a1_v, a1_p, b1_v, b1_p`
- 集合竞价期间不产生成交(skip=True不返回), a1_p/b1_p 为虚拟匹配价

```python
d = get_ticks("000001.XSHE", start_dt=None, end_dt="2018-07-02", count=10)
# 返回 numpy.ndarray, 每行: (time, current, high, low, volume, money)
```

### get_call_auction — 集合竞价

```python
get_call_auction(security, start_date=None, end_date=None, fields=None)
# 获取交易日 09:25 的集合竞价快照
# 支持股票(2010起)/场内基金(2019起)/指数(2017起)/上交所ETF期权(2017起)
# start_date/end_date 均不能为None, 最多返回5000条
```

---

## 5. 财务数据

### get_fundamentals — 单日财务查询

```python
get_fundamentals(query_object, date=None, statDate=None)
```
- `date`：查指定日期收盘后能看到的最新财报（无未来函数）。回测中默认 `context.current_dt` 前一天
- `statDate`：查指定报告期，格式 `'2015q1'` / `'2015'`（可能引入未来函数）
- 两参数只能传一个；都不传等价于 `date=None` 取默认值
- `query_object`：由全局 `query()` 构建的 SQLAlchemy Query 对象
- 返回 `DataFrame`，最多 5000 行
- 常用表：`valuation`(市值), `balance`(资产负债), `income`(利润), `cash_flow`(现金流), `indicator`(财务指标)
- 银行/券商/保险专项数据只有年报，需传 `statDate`

```python
# 单只股票市值
q = query(valuation).filter(valuation.code == '000001.XSHE')
df = get_fundamentals(q, '2015-10-15')

# 多表联合 + 多条件
df = get_fundamentals(query(
    valuation.code, valuation.market_cap, valuation.pe_ratio, income.total_operating_revenue
).filter(
    valuation.market_cap > 1000,
    valuation.pe_ratio < 10,
    income.total_operating_revenue > 2e10
).order_by(valuation.market_cap.desc()).limit(100), date='2015-10-15')

# 按季度查询
rets = [get_fundamentals(q, statDate='2014q'+str(i)) for i in range(1,5)]
```

### get_fundamentals_continuously — 连续多日财务

```python
get_fundamentals_continuously(query_object, end_date=None, count=None, panel=True)
# 限制: 标的数 × count ≤ 5000
# 建议 panel=False 返回 DataFrame
```

### get_history_fundamentals — 多季度/年度财务

```python
get_history_fundamentals(security, fields, watch_date=None, stat_date=None,
    count=1, interval='1q', stat_by_year=False)
# watch_date: 查询此日期前发布的报表
# stat_date: 查询指定报告期及之前的历史报告期
# watch_date / stat_date 必须指定一个
# interval: '1q'(季度间隔) / '1y'(年度间隔)
# stat_by_year=True: interval必须'1y', fields可选银行/券商/保险专项表
# stat_by_year=False: fields仅支持 balance/income/cash_flow/indicator
# 不支持 valuation 表, 最多5000行
```

### get_valuation — 市值表

```python
get_valuation(security, start_date=None, end_date=None, fields=None, count=None)
# 字段: capitalization, circulating_cap, market_cap(总市值亿), circulating_market_cap,
#       turnover_ratio(换手率%), pe_ratio(PE,TTM), pe_ratio_lyr(PE), pb_ratio, ps_ratio, pcf_ratio
# 返回 DataFrame(含 code+day 列), 最多5000行
# ⚠️ 不要获取当天的 PE/市值(盘后更新)
```

### 其他数据获取

```python
get_extras(info, security_list, start_date='2015-01-01', end_date='2015-12-31', df=True, count=None)
# info: 'is_st'(是否ST) / 'acc_net_value'(基金累计净值) / 'unit_net_value'(基金单位净值)
#        / 'futures_sett_price'(期货结算价) / 'futures_positions'(期货持仓量) / 'adj_net_value'(场外基金复权净值)
# count 与 start_date 二选一

get_money_flow(security_list, start_date=None, end_date=None, fields=None, count=None)
# 资金流向(仅股票,天频,2010起)
# 字段: date, sec_code, change_pct(涨跌幅),
#       net_amount_main/pct_main(主力净额/净占比=超大单+大单),
#       net_amount_xl/pct_xl(超大单: ≥50万股或100万),
#       net_amount_l/pct_l(大单: ≥10万股或20万且<50万股或100万),
#       net_amount_m/pct_m(中单), net_amount_s/pct_s(小单)

get_billboard_list(stock_list, start_date, end_date, count)
# 龙虎榜数据 → DataFrame(含 buy_value, sell_value, net_value, amount 等)

finance.run_query(query_object)
# 查询深沪港通/股东信息/公司概况, 最多4000行, 不支持多表联查

macro.run_query(query_object)
# 查询宏观经济数据, 最多4000行, 不支持多表联查
```

---

## 6. 标的信息

```python
get_all_securities(types=[], date=None)
# types: 'stock'|'fund'|'index'|'futures'|'options'|'etf'|'lof'|'fja'|'fjb'|'open_fund'|
#         'bond_fund'|'stock_fund'|'QDII_fund'|'money_market_fund'|'mixture_fund'
# types=[] → 返回所有股票(不含基金/指数/期货)
# date: 指定日期的上市股票, None=所有历史
# 返回 DataFrame(index=代码, columns=[display_name, name, start_date, end_date, type])

get_security_info(code, date=None)
# 返回对象属性: display_name, name, start_date, end_date, type, parent(分级基金母基)

get_all_trade_days()
# 返回所有交易日的 numpy.ndarray (每个元素 datetime.date)

get_trade_days(start_date=None, end_date=None, count=None)
# 返回 list[datetime.date], 最多到当前年份最后一天

get_trade_day(security, query_dt)
# 返回 dict(代码→对应交易日date)。有夜盘的期货跨日前返回下一交易日

get_index_stocks(index_symbol, date=None)
# 回测中默认 context.current_dt; 研究中默认今天

get_index_weights(index_id, date=None)
# 返回 DataFrame(code, display_name, date, weight)

get_industry_stocks(industry_code, date=None)  # 例: 'I64'=计算机
get_concept_stocks(concept_code, date=None)     # 例: 'SC0084'=风电

get_industries(name, date=None)
# name: 'sw_l1'/'sw_l2'/'sw_l3' / 'jq_l1'/'jq_l2' / 'zjw'(证监会)

get_concepts()
# 返回 DataFrame(index=概念代码, columns=[name, start_date])

get_industry(security, date=None)
# 返回 dict(代码→{jq_l1/jq_l2/sw_l1/sw_l2/sw_l3/zjw: {industry_code, industry_name}})

get_concept(security, date=None)
# 返回 dict(代码→{'jq_concept': [{concept_code, concept_name}, ...]})
```

---

## 7. 因子&库

```python
from jqfactor import get_all_factors, get_factor_values, get_factor_kanban_values

get_all_factors()
# → DataFrame: index(因子代码), factor(因子名), factor_intro, category

get_factor_values(securities, factors, start_date, end_date, count)
# 返回 dict(因子名 → DataFrame(index=日期, columns=股票代码))
# 限制: 因子数 × 股票数 × 交易日 ≤ 200,000

# Alpha 101 (WorldQuant)
from jqlib.alpha101 import *
a = alpha_001('2017-03-10', '000300.XSHG')  # 返回 Series(代码→因子值)
a['000001.XSHE']

# Alpha 191 (国泰君安)
from jqlib.alpha191 import *
code = list(get_all_securities(['stock']).index)
a = alpha_007(code, end_date='2017-04-04')

# 技术分析指标
from jqlib.technical_analysis import *
gdx_jax, gdx_ylx, gdx_zcx = GDX(security_list, check_date='2017-01-04', N=30, M=9)
# 返回 dict(代码→值)
```

---

## 8. 交易下单

### 四个核心下单函数

```python
order(security, amount, style=None, side='long', pindex=0, close_today=False)
```
- `amount`：正数=买，负数=卖（A股：100股整数倍，卖光时无限制；科创板：200起可零散）
- `style`：`None`=市价单；`LimitOrderStyle(limit_price)`=限价单；`MarketOrderStyle(limit_price)`=科创板市价单+保护价
- `side`：`'long'`/'`short'`（股票基金不支持开空）
- `pindex`：子账户序号（0 开始）
- `close_today`：`True`=只平今仓，`False`=优先平昨仓（仅上海能源/上期所/中金所生效；其他交易所先开先平）
- 返回 `Order` 对象或 `None`（失败）
- 失败原因：停牌/未上市/退市/代码错误/保证金不足/科创板市价单未指定保护价/给股票开空单

```python
order_target(security, amount, style=None, side='long', pindex=0, close_today=False)
# 调仓到目标股数(amount=0=全卖)。自动撤销该标的已有未完成订单。
# 其他参数同 order

order_value(security, value, style=None, side='long', pindex=0, close_today=False)
# value = 最新价 × 手数 × 保证金率(股票=1) × 乘数(股票=100)
# 例: order_value('000001.XSHE', 10000) → 买入约 10000 元

order_target_value(security, value, style=None, side='long', pindex=0, close_today=False)
# 调仓到目标价值(value=0=全卖)。自动撤销该标的已有未完成订单。
```

### 停止单

```python
StopMarketOrderStyle(mode, stop_price)
StopLimitOrderStyle(mode, stop_price, limit_price)
# mode: 'stop_loss'(止损) / 'take_profit'(止盈)
# 止损单: 买入触发价 > 最新价, 卖出触发价 < 最新价
# 止盈单: 相反
# 不满足条件时立即触发; 不会提前锁定持仓和资金; 当天未触发盘后撤销
# order_value/order_target_value 用 stop_price/limit_price 计算委托数量
```

### 订单管理

```python
cancel_order(order)
# 传 Order对象 或 order_id; 返回 Order/None

get_open_orders()
# 当天所有未完成订单 → dict(order_id → Order)

get_orders(order_id=None, security=None, status=None)
# 查询订单(仅当天), 可按 order_id/代码/OrderStatus 筛选

get_trades()
# 当天所有成交记录 → dict(trade_id → Trade)
# 一个订单可能产生多条成交

inout_cash(cash, pindex=0)
# cash>0=入金, cash<0=出金。即时到账, 计入当日成本。

batch_submit_orders(orders)
# orders: [{'security':'xxx','amount':xxx,'style':...,'side':'long'}, ...]
# 任一个校验失败则整批失败

batch_cancel_orders(orders)
# orders: list[Order/order_id]
```

---

## 9. 组合优化

```python
from jqlib.optimizer import *

portfolio_optimizer(date, securities, target, constraints,
    bounds=[Bound(0.0, 1.0)], default_port_weight_range=[0.0, 1.0],
    ftol=1e-9, return_none_if_fail=True)
# 返回 Series(代码→权重) 或 None(失败: return_none_if_fail=True时)
```

**目标函数 target** (九选一):

| 目标 | 参数 | 说明 |
|------|------|------|
| `MinVariance(count=250)` | count: 向前取returns天数 | 最小化组合方差 |
| `MaxProfit(count=250)` | count: 同上 | 最大化组合收益 |
| `MaxSharpeRatio(rf=0.0, weight_sum_equal=1.0, count=250)` | rf: 无风险利率 | 最大化夏普比 |
| `MinTrackingError(benchmark, count=250)` | benchmark: str基准代码 | 最小化跟踪误差 |
| `RiskParity(count=250, risk_budget=None)` | risk_budget: Series(代码→预算) | 风险平价, None=等风险贡献 |
| `MaxScore(scores)` | scores: Series(代码→打分) | 打分高的权重高 |
| `MinScore(scores)` | scores: Series(代码→打分) | 打分低的权重高 |
| `MaxFactorValue(factor, count=1)` | factor: Factor子类实例 | 因子值大的权重高(仅股票) |
| `MinFactorValue(factor, count=1)` | factor: Factor子类实例 | 因子值小的权重高(仅股票) |

**限制函数 constraints** (常用):

| 约束 | 说明 |
|------|------|
| `WeightConstraint(low=0.0, high=1.0)` | 组合总权重范围 |
| `WeightEqualConstraint(limit=1.0)` | 组合总权重固定值 |
| `AnnualStdConstraint(limit, count=250)` | 年化标准差上限 |
| `AnnualProfitConstraint(limit, count=250)` | 年化收益下限 |
| `IndustryConstraint(['HY007'], low=0, high=0.2)` | 行业权重限制 |
| `IndustriesConstraint('jq_l1', low=0, high=0.2)` | 整个行业分类下每个行业都受此限制 |
| `MarketConstraint('stock', low=0, high=0.2)` | 市场(类型)权重限制 |
| `BarraConstraint(size=[-0.5,0.5], 等, standardlize=True, winsorize=True)` | 10个Barra风险因子暴露限制 |
| `TurnoverConstraint(limit, current_portfolio=None)` | 换手率限制 |
| `TrackingErrorConstraint(benchmark, limit, count=250)` | 年化跟踪误差限制 |
| `MaxDrawdownConstraint(-0.25)` | 最大回撤限制 |
| `RatioConstraint(ratio, low, high, rf, benchmark, count=250)` | 比率限制（sharpe_ratio/information_ratio/calmar_ratio/omega_ratio/sortino_ratio/var/cvar） |
| `ExposureConstraint(Factor子类, low=0, high=1, count=1)` | 因子暴露限制 |
| `IndustryDeviationConstraint(industry_code, benchmark, limit)` | 行业权重与基准偏离度 |
| `IndustriesDeviationConstraint(industry_code, benchmark, limit)` | 行业分类权重与基准偏离度 |

**边界函数 bounds**:

```python
Bound(low=0.0, high=0.1)                                      # 每只标的权重范围
IndustryBound(['HY001','HY007'], low=0, high=0.05)             # 指定行业标的权重
LiquidityBound(limit, capital, count=1, subset=None)           # 不超过成交量×limit
# 例: LiquidityBound(0.5, capital=1000000, count=5)
CapBound(limit, capital, count=1, subset=None)                # 不超过市值×limit
# 例: CapBound(0.025, capital=100000000)
```

---

## 10. 数据处理

```python
from jqfactor import neutralize, winsorize, winsorize_med, standardlize

neutralize(data, how=['jq_l1','market_cap'], date=None, axis=1, fillna=None, add_constant=False)
# data: pd.Series / pd.DataFrame (index=股票代码)
# how: 行业分类('jq_l1'→聚宽一级) / 财务字段('market_cap') / 对数市值('ln_market_cap')
#       / 聚宽因子库因子名 / 风险因子('size','beta','momentum',...)
# fillna: 行业分类代码, 用该行业均值填充缺失值(行业代码: 'jq_l1'/'sw_l1'等)
# axis: data为DataFrame时, 0=按列, 1=按行

winsorize(data, scale=None, range=None, qrange=None, inclusive=True, inf2nan=True, axis=1)
# scale/range/qrange 三选一
#   scale: 标准差倍数 [μ - N×σ, μ + N×σ]
#   range: [lower, upper] 固定边界
#   qrange: [0.05, 0.95] 分位数边界
# inclusive=True: 边界外替换为边界值; False: 替换为 np.nan
# inf2nan=True: 先替换 np.inf/-np.inf 为 np.nan

winsorize_med(data, scale=1, inclusive=True, inf2nan=True, axis=1)
# 中位数去极值: [med - scale×distance, med + scale×distance]
# distance = ABS(因子值 - med) 的中位数

standardlize(data, inf2nan=True, axis=1)
# z-score标准化: (x - mean) / std
```

---

## 11. 对象

### g — 全局变量

```python
g.security = '000001.XSHE'           # 正常变量, pickle序列化持久化
g.__query = query(valuation)         # '__'前缀: 不序列化, 用于不可pickle对象
# ⚠️ 序列化状态上限30M; IO对象(文件/网络/DB连接)不可序列化
# ⚠️ 不要在函数体外声明全局变量(每次进程重启都会执行)
```

### context — 策略上下文

| 属性 | 类型 | 说明 |
|------|------|------|
| `current_dt` | `datetime.datetime` | 当前逻辑时间 (UTC+8) |
| `previous_date` | `datetime.date` | 前一个交易日 |
| `portfolio` | `Portfolio` | 总账户汇总 (单仓位时指向 subportfolios[0]) |
| `subportfolios` | `list[SubPortfolio]` | 子账户列表 |
| `universe` | `list` | `set_universe()` 设定的股票池 |
| `run_params.start_date` | `datetime.date` | 回测开始日期 |
| `run_params.end_date` | `datetime.date` | 回测结束日期 |
| `run_params.type` | `str` | `'simple_backtest'` / `'full_backtest'` / `'sim_trade'` |
| `run_params.frequency` | `str` | `'day'` / `'minute'` / `'tick'` |

> context 也可以像 `g` 一样添加自定义变量并持久化，以 `__` 开头的不持久化。但建议使用 `g`。

### Portfolio (总账户) / SubPortfolio (子账户)

| 属性 | 说明 |
|------|------|
| `available_cash` | 可用资金 |
| `transferable_cash` | 可取资金(不含今日卖出所得) |
| `locked_cash` | 挂单锁住资金 |
| `total_value` | 总权益(现金 + 持仓市值) |
| `positions_value` | 持仓总价值 |
| `starting_cash` (=`inout_cash`) | 初始资金 |
| `returns` | 累计收益 (前一日 total_value / inout_cash) |
| `margin` | 保证金 (股票基金=100%, 两融=0, 期货=持仓市值×保证金比率) |
| `long_positions` | `dict(代码 → Position)` |
| `short_positions` | `dict(代码 → Position)` |
| `positions` | `= long_positions` |
| `inout_cash` | 累计出入金 |
| **仅 SubPortfolio** | |
| `type` | 账户类型字符串 |
| `total_liability` | 总负债(两融) |
| `net_value` | 净资产(total_value - total_liability) |
| `maintenance_margin_rate` | 维持担保比例(两融) |
| `available_margin` | 融资融券可用保证金 |

### Position — 持仓

| 属性 | 说明 |
|------|------|
| `security` | 标的代码 |
| `price` | 最新行情价 |
| `total_amount` | 总仓位(不含冻结) |
| `closeable_amount` | 可卖出仓位 |
| `locked_amount` | 挂单冻结仓位 |
| `today_amount` | 今日开仓量 |
| `value` | 标的价值 = `price × total_amount × multiplier` (股票/基金 multiplier=1) |
| `avg_cost` | 持仓成本 — 只在开仓/加仓时更新, 卖出时不变。用于计算浮动盈亏 |
| `acc_avg_cost` | 累计持仓成本 — 减仓时也会更新, 用于计算累积盈亏。初始(0,0), 加仓: `(cost×amt + trade_value + commission)/(amt + trade_amt)`; 减仓: `(cost×amt - trade_value + commission)/(amt - trade_amt)` |
| `hold_cost` | 当日持仓成本 |
| `init_time` | 建仓时间 `datetime` |
| `transact_time` | 最后交易时间 `datetime` |
| `side` | `'long'` / `'short'` |
| `pindex` | 仓位索引 |

### SecurityUnitData — data 对象

| 属性/方法 | 说明 |
|------|------|
| `open` | 开盘价 (天级09:27后可获取) |
| `close` | 收盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `volume` | 成交量(股) |
| `money` | 成交额 |
| `factor` | 前复权因子 (`close/factor`=真实价格) |
| `high_limit` | 涨停价 |
| `low_limit` | 跌停价 |
| `avg` (=`price`, 已废弃) | 均价 |
| `pre_close` | 前收盘价(分钟频率 `pre_close=open`) |
| `paused` | 是否停牌(bool) |
| `security` | 标的代码 |
| `returns` | 本周期收益率 `(close-pre_close)/pre_close` |
| `isnan()` | 数据是否无效(退市/未上市→True) |
| `mavg(days, field='close')` | 过去 days 天 field 的均值(跳过停牌, 不足返NaN) |
| `vwap(days)` | 过去 days 天均价的成交量加权平均 |
| `stddev(days)` | 过去 days 天收盘价的标准差(跳过停牌) |

### Tick

| 属性 | 说明 |
|------|------|
| `code` | 标的代码 |
| `datetime` | tick 发生时间 |
| `current` | 最新价 |
| `open` | 当日开盘价 |
| `high` / `low` | 日内最高/最低(截至此刻) |
| `volume` / `money` | 累计成交量/成交额 |
| `position` | 持仓量(仅期货) |
| `a1_p~a5_p` / `a1_v~a5_v` | 卖一价到卖五价/量(期货仅一档) |
| `b1_p~b5_p` / `b1_v~b5_v` | 买一价到买五价/量(期货仅一档) |

### Order — 订单

| 属性 | 说明 |
|------|------|
| `order_id` | 订单ID |
| `security` | 标的代码 |
| `is_buy` | 是否为买 (期货: 开多/平空=买; 开空/平多=卖) |
| `amount` | 下单数量(正数) |
| `filled` | 已成交数量(正数) |
| `price` | 平均成交价 |
| `avg_cost` | 买=成交均价; 卖=卖前持仓成本(用于算收益) |
| `status` | `OrderStatus` 枚举 |
| `side` | `'long'` / `'short'` |
| `action` | `'open'` / `'close'` |
| `commission` | 交易费用(佣金+印花税) |
| `add_time` | 委托时间 |

> ⚠️ 不可跨交易日保存 Order 对象。

### OrderStatus 枚举

```python
class OrderStatus(Enum):
    new = 8        # 新创建未委托(盘前/隔夜, 开盘时→open)
    open = 0       # 已委托, 无成交
    filled = 1     # 部分成交
    canceled = 2   # 已撤销(可能部分成交)
    rejected = 3   # 已被交易所拒绝(可能部分成交)
    held = 4       # 全部成交
# 判断: str(order.status) == 'held'
```

### Trade — 成交记录

```python
time / security / amount / price / trade_id / order_id
```

---

## 12. Tick策略

前提：策略频率=tick + 开启动态复权 + 有tick权限。

```python
handle_tick(context, tick)
# 订阅的标的产生 tick 时被调用

subscribe(security, 'tick')
# 订阅标的的 tick 事件
# security: 支持股票/期货/中证指数/场内基金，不能订阅主力合约/指数合约
# 回测不限订阅数，模拟最多 100 个标的

unsubscribe(security, 'tick')   # 取消订阅指定标的
unsubscribe_all()               # 取消全部订阅
```

```python
# 完整示例:
def initialize(context):
    init_cash = context.portfolio.starting_cash
    set_subportfolios([SubPortfolioConfig(cash=init_cash, type='futures')])
    g.code1 = 'RB1909.XSGE'
    run_daily(before_market_open, time='08:30', reference_security='RB9999.XSGE')
    run_daily(after_market_close, time='15:30', reference_security='RB9999.XSGE')

def before_market_open(context):
    subscribe(g.code1, 'tick')

def handle_tick(context, tick):
    tick_data = get_current_tick(g.code1)

def after_market_close(context):
    unsubscribe_all()
```

---

## 13. 分仓/期货/两融

### 分仓

```python
set_subportfolios([SubPortfolioConfig(cash, type), ...])
# type: 'stock'(股票+基金) / 'index_futures'(金融期货) / 'futures'(所有期货) / 'stock_margin'(两融)
# 各 cash 之和 = 初始资金, 只能在 initialize 中调用
# 默认 subportfolios[0] = type='stock'
# 最多 100 个子账户

transfer_cash(from_pindex, to_pindex, cash)
# 从 from 子账户转 cash 到 to 子账户, 即时到账
```

### 期货

```python
# 初始化
set_subportfolios([SubPortfolioConfig(cash=init_cash, type='futures')])

# 交易: order/order_target 按手数; order_value/order_target_value 按保证金
# 下单时必须指定 reference_security (如 'RB9999.XSGE')
# get_price/history/attribute_history/get_current_data/get_bars 均可用
# 新增字段: 'open_interest'(持仓量)
# get_price 取天数据时 pre_close = 前结算价

get_dominant_future(underlying_symbol, dt)
# 获取主力合约代码。例: get_dominant_future('RB', '2019-01-04') → 'RB1905.XSGE'

get_future_contracts(underlying_symbol, dt)
# 返回可交易合约列表

futures_margin_rate(security, rate)
# 设置期货保证金比率

is_dangerous(context, pindex=0)
# 是否保证金不足 → True/False
```

### 两融

```python
# 初始化两融账户
set_subportfolios([SubPortfolioConfig(cash=init_cash, type='stock_margin')])

margincash_open(security, amount, ...)          # 融资买入
margincash_close(security, amount, ...)         # 卖券还款
margincash_direct_refund(security, amount, ...) # 直接还款
marginsec_open(security, amount, ...)           # 融券卖出
marginsec_close(security, amount, ...)          # 买券还券
marginsec_direct_refund(security, amount, ...)  # 直接还券

margincash_interest_rate(rate)                  # 设置融资利率
margincash_margin_rate(security, rate)          # 设置融资保证金比率
marginsec_interest_rate(rate)                   # 设置融券利率
marginsec_margin_rate(security, rate)           # 设置融券保证金比率

get_margincash_stocks()    # 融资标的列表
get_marginsec_stocks()     # 融券标的列表 (⚠️当天数据未生成)
get_mtss()                 # 融资融券信息
```

---

## 14. 工具函数

```python
record(**kwargs)
# ♠ 画图函数。key=曲线名, value=数值(不能是列表)。
# 按天绘图, 分钟回测取当天最后一次调用值。16:00 后属于第二天。
# 示例: record(price=current_price, open=d.open, close=d.close)

send_message(message, channel='weixin')
# ♠ 仅实时模拟交易可用。每天最多5条, 每条≤200字符, 不能含回车/换行。
# 需绑定微信。回测中直接忽略, 不报错。

log.info(content)       # 信息
log.warn(content)       # 警告
log.error(content)      # 错误
log.debug(content)      # 调试
log.set_level(name, level)
# name: 'order'(order系列API日志) / 'history'(数据API日志) / 'strategy'(用户日志) / 'system'(其他)
# level: 'debug' < 'info' < 'warning' < 'error'
# 默认所有级别为debug。建议保持默认(不设置或设order为info)。

write_file(path, content, append=False)
# 写入文件到研究根目录(相对路径)。content: str/unicode(UTF-8编码)/二进制。
# 例: write_file("test.txt", "hello world")
# 例: write_file('df.csv', df.to_csv())

read_file(path)
# 读取研究根目录文件, 返回原始 bytes 内容(不做decode)。
# Python3 读csv/Excel 需用 BytesIO body 再 pd.read_csv(BytesIO(body))
# Python2 用 StringIO
# ⚠️ 不能读取本地未上传的文件

create_backtest(algorithm_id, start_date, end_date, frequency="day",
    initial_cash=10000, initial_positions=None, extras=None, name=None,
    code="", benchmark=None, python_version=2, use_credit=False)
# 研究中创建回测 → 返回 backtest_id
# initial_positions: [{'security':'xxx','amount':'100','avg_cost':'1.0'}, ...]
# extras: dict, 在initialize之后赋给g(会覆盖initialize中的同名变量)
# code: 直接传入策略代码字符串
# use_credit: 是否允许消耗积分(每30分钟2积分)

get_backtest(backtest_id)
# 研究中获取回测/模拟信息。返回对象:
#   .get_status()   # 'none'|'running'|'done'|'failed'|'canceled'|'paused'|'deleted'
#   .get_params()   # dict, 创建时传入的所有参数
#   .get_results()  # list[dict], 每个交易日{time, returns, benchmark_returns}
#   .get_positions(start_date, end_date) # list[dict]
#   .get_orders(start_date, end_date)    # list[dict]
#   .get_records()  # list[dict], 所有record()记录
#   .get_risk()     # dict, 总风险指标
#   .get_period_risks() # dict, 分月风险指标
#   .get_balances(start_date, end_date)  # list[dict]

normalize_code(codes)
# 将其他格式代码转聚宽格式 → list
# '000001' / 'SZ000001' / '000001SZ' / '000001.sz' → '000001.XSHE'

enable_profile()
# ♠ 回测专用。放代码最上方, 运行回测后看到每行耗时分析。
```

---

## 15. 关键规则

### 时间与K线

| 规则 | 说明 |
|------|------|
| K线后对齐 | K线时间 = 数据结束时间。如 09:31 的K线 = 09:25:00~09:30:59 |
| 分钟K线 | 每天240根 (09:31~15:00, 无09:30和11:30的K线) |
| 日频数据 | 不含当天（收盘后也不含）；分钟数据不含当前分钟 |
| 当天数据 | 用 `get_current_data()` 获取开盘价/涨跌停等 |

### 撮合规则

| 规则 | 说明 |
|------|------|
| 市价单 | 成交价 = 最新价 ± 滑点；回测成交量 ≤ 当日总量 × `order_volume_ratio` |
| 限价单 | 买入: 委托价 ≥ 最新价+滑点成交；卖出: 委托价 ≤ 最新价-滑点成交；剩余挂单按Bar/Tick撮合 |
| 涨停时 | 市价买单撤销；限价单挂单 |
| 跌停时 | 市价卖单撤销；限价单挂单 |
| 每日撤单 | 交易日结束后所有未完成订单自动取消 |
| 下单上限 | 每日最多 10000 笔 |
| 非交易时间下单 | 市价单/限价单均挂单，开盘后撮合 |

### 复权

| 规则 | 说明 |
|------|------|
| `use_real_price=True` | 下单用真实价格；`history`/`attribute_history`/`get_price` 返回基于当天日期的前复权价 |
| 不同日期调用 | 返回价格可能不同(复权因子更新), **不要跨日期缓存** |
| 真实价格获取 | `df['close'][-1] / df['factor'][-1]` |
| 期货 | `use_real_price` 对期货不生效 |
| 场内基金 | 复权可能有偏差(除权日披露不标准), 不建议开启动态复权 |

### 模拟盘注意事项

| 规则 | 说明 |
|------|------|
| 状态持久化 | 每天结束后用 pickle 保存 g 和 context |
| `__` 前缀变量 | 不被序列化保存 |
| 不序列化的对象 | `query(valuation)` / `open()` / `requests.get()` 等 IO 对象 |
| 状态上限 | 30M (超过 20M 日志警告) |
| initialize | 全局仅执行一次, 改代码不会重新执行 |
| process_initialize | 每次进程启动都执行(模拟盘每天) |
| 延迟 | 模拟盘有 ~10s 系统延迟；从创建到启动有 2-3 分钟延迟 |
| 函数超时 | 1800 秒 |
| 内存上限 | 3G |
| 数据更新 | T+1 的 00:01 |

### 股票代码格式

```
深交所(深圳):  '000001.XSHE'
上交所(上海):  '600000.XSHG'
中金所(金融期货): 'IF1901.CCFX'
上期所(商品):   'RB1901.XSGE'
大商所(商品):   'M1901.XDCE'
郑商所(商品):   'SR1901.XZCE'
上能源:        'SC1901.XINE'
创业板:        '300001.XSHE'
科创板:        '688001.XSHG'
指数:          '000300.XSHG' (沪深300)
基金(场内):     '510050.XSHG'
期权:          '10001743.XSHG'
```

### 手续费默认值

| 品种 | open_tax | close_tax | open_commission | close_commission | close_today_commission | min_commission |
|------|----------|-----------|-----------------|------------------|------------------------|----------------|
| stock | 0 | 0.001 | 0.0003 | 0.0003 | 0 | 5 |
| index_futures | 0 | 0 | 0.000023 | 0.000023 | 0.0023 | 0 |

---

## 16. 常见坑点 / JQBoson 引擎兼容性 Quirks

> 以下为聚宽 JQBoson 回测引擎(Python 3.6 环境)的非标准行为,在原生 CPython 中正常,在聚宽中会**静默出错**。从其他平台移植策略时务必逐一排查。

### 16.1 `sum(dict.values())` 不会归约

**症状**:
```python
d = {'a': 1.0, 'b': 2.0, 'c': 3.0}
x = sum(d.values())
# 标准 CPython: x = 6.0 (float)
# 聚宽 JQBoson:  x = dict_values([1.0, 2.0, 3.0]) ← 仍是 dict_values, 不会归约!
y = x / 100.0
# TypeError: unsupported operand type(s) for /: 'dict_values' and 'float'
```

**触发场景**:对 `dict.values()` / `dict.items()` / `pd.Series.values` 等迭代器直接 `sum()`。

**修复**:**必须**先转 `list` 再 sum。
```python
# ❌ 错误
total = sum(d.values())

# ✅ 正确
total = sum([d[_k] for _k in d])

# ✅ 同样正确 (仅当 value 一定是数值时)
total = sum(list(d.values()))
```

**额外建议**:对 `total_value`、`available_cash` 这类除数先做 `> 0` 守卫,避免空 dict 触发除零。

### 16.2 `order_value` 是"追加",不是"调仓到目标"

**症状**:
```python
# 已持有 1000 元股票, 想调仓到 5000 元
order_value(stock, 5000)
# 期望: 持仓变为 5000 元
# 实际: 持仓变为 6000 元 (追加 5000)
```

**修复**:调仓场景必须用 `order_target_value`:
```python
# ✅ 正确
order_target_value(stock, 5000)   # 持仓变为 5000
order_target_value(stock, 0)      # 全部卖出
```

`order_value` 仅适用于"想再补仓 N 元"的场景。

### 16.3 `cd[stock]` 对退市/异常股票抛 KeyError

**症状**:`get_current_data()` 返回的 dict 不包含退市/退市整理期/数据缺失的股票,直接 `cd[s].paused` 抛 KeyError 终止策略。

**修复**:用 `cd.get(s)` 拿 None,或 `try/except` 守护。
```python
# ❌ 错误
if cd[s].paused: continue

# ✅ 正确
d = cd.get(s)
if d is None or d.paused: continue
```

### 16.4 `get_current_data()` 没有 `volume` 字段

`cd[stock]` 只有 `last_price, high_limit, low_limit, paused, is_st, day_open, name, industry_code`,**无 `volume` / `money` / `avg`**。

`history()` / `attribute_history()` 同样**不含当天**(收盘后也不含)。如需当日量比,只能:
1. 用昨天成交量近似(1 日滞后,大多数场景可接受)
2. 用 `get_bars(..., include_now=True, ...)` 在 14:55 取当日未完成 bar

### 16.5 `high_limit` / `low_limit` 可能为 0

新股上市首日 / 数据缺失时,这两个字段可能为 0,直接比较 `last_price >= high_limit` 会**恒真**(last_price ≥ 0),导致永远跳过买入/卖出。

**修复**:加 `> 0` 守卫。
```python
# ❌ 错误
if last_price >= cd[stock].high_limit: continue

# ✅ 正确
if cd[stock].high_limit > 0 and last_price >= cd[stock].high_limit: continue
```

### 16.6 模拟盘 `run_daily` 每日触发(含周末/节假日)

**回测**:`run_daily` 仅在交易日触发。

**模拟盘**:`run_daily` 文档写"每天 09:00 执行",会**每日触发**。`g.rebalance_counter += 1` 在周末递增,会破坏 `rebalance_freq_days` 的"交易日"语义。

**修复**:在每个回调开头加交易日守卫。
```python
def _is_trading_day(context):
    today = np.datetime64(context.current_dt.date())
    return today in g.trade_days_set  # 启动时缓存 get_all_trade_days()

def before_market_open(context):
    if not _is_trading_day(context):
        return
    ...
```

### 16.7 涨跌停/停牌时 `order_target_value` 自动挂单,不会失败

当股票**跌停封板**或**停牌**时调用 `order_target_value(stock, 0)`,**不会**返回 `None`,而是返回一个**挂单** Order,等股票打开跌停/复牌后自动撮合,无须次日重发。

**因此**:`execute_rebalance` 清仓段遇到跌停/停牌**不需要**跳过,直接发单即可。`if sell_order is None` 永远为 False。

### 16.8 科创板 (688xxx) 市价单需要指定保护限价

**症状**:下单科创板股票时报错:
```
订单委托失败: StockOrder(security=688981.XSHG mode=OrderAmount ...
  error=科创板市价单需要指定保护限价,取值必须大于 0 且小于 1 万元)
```

**原因**:聚宽对**科创板 (688xxx)**的市价单 (`MarketOrderStyle`)有特殊限制——
交易所规则要求市价单必须带"保护限价"(price collar),防止市价单瞬间打到极端价位。
因此 `order(stock, shares)` (默认市价单) 在科创板上会失败。

**修复**:对科创板单独用 `LimitOrderStyle(limit_price)` 下限价单:
```python
# ❌ 错误 (科创板会失败)
if stock.startswith('688'):
    order(stock, delta_shares)  # 默认 MarketOrderStyle → 失败

# ✅ 正确 (科创板用限价单)
if stock.startswith('688'):
    limit_price = min(last_price * 1.005, 9999.99)  # 略高于当前价, 保险成交
    order(stock, delta_shares, LimitOrderStyle(limit_price))
else:
    order(stock, delta_shares)  # 主板/中小创仍用市价单
```

**关键约束**:
- 限价必须 `> 0`
- 限价必须 `< 10000` 元(科创板高价股用 `last_price * 1.005` 通常满足)
- 限价 `last_price * 1.005` 比当前价高 0.5%,既能成交又防止异常

**适用场景**:HS300 / 科创50 / 任何包含科创板的 universe。代码里用 `stock.startswith('688')` 判定。

### 16.9 `order_target_value` / `order_value` 内部"下单数量为0"假报

**症状**:用户计算的目标股数明显 > 0(例如 58 lots),JQuant 仍报:
```
下单失败,初步检查下单数量为0: OrderTargetValue(_value=25584.0 style=MarketOrderStyle ...)
```

**修复**:用 `order(stock, delta_shares)` 直接传股数,自己算 `target_shares` 和 `current_shares`:
```python
# ❌ 错误 (偶尔报"数量为0")
order_target_value(stock, value)
order_value(stock, value)

# ✅ 正确 (精确控制)
target_shares = int(value // (lot_size * last_price)) * lot_size
current_shares = pos.total_amount if pos else 0
delta_shares = target_shares - current_shares
order(stock, delta_shares)  # 直接传股数, JQuant 不再内部推算
```

**额外提示**:科创板 + `order_target_value` 双重触发,**双重失败**——既要 16.8 的限价单,又要避开 16.9 的股数 0 bug。

### 16.10 `g.params = PARAMS` 可能丢失长列表 / 嵌套结构

**症状**:`KeyError: 'xxx'` 出现在 PARAMS dict 里**明明有**的键。

**原因**:聚宽 JQBoson 对全局变量 `g.params` 写入有大小/嵌套深度限制,如果 PARAMS 中含**长度 > ~100 的 list** (如 300 只股票池)、**多层嵌套 dict** 等复杂结构,会被**截断或丢弃**,导致 `g.params` 中缺失部分键。

**修复**:把大列表/嵌套结构放到独立的模块级变量,而不是放在 PARAMS 里:
```python
# ❌ 错误 (PARAMS 含 300 项列表 → g.params = PARAMS 后丢键)
PARAMS = {
    'universe_index': '000300.XSHG',
    'static_universe': True,
    'hs300_codes': [300 个代码],   # ← 这个列表会让 PARAMS 过大
    'ma_long': 30,
    'atr_threshold': 0.08,
    ...
}
g.params = PARAMS
# KeyError: 'ma_long'  ← ma_long 在 PARAMS 中, 但 g.params 中丢了!

# ✅ 正确 (大列表拆到独立模块级变量)
PARAMS = {
    'universe_index': '000300.XSHG',
    'static_universe': True,
    'ma_long': 30,
    'atr_threshold': 0.08,
    ...
}
HS300_STATIC = [300 个代码]  # ← 独立的模块级 list
g.params = PARAMS  # PARAMS 中所有键都保留
# 在 before_market_open 中:
if PARAMS.get('static_universe', False):
    raw = list(HS300_STATIC)  # 直接引用模块级变量
```

**经验法则**:
- PARAMS 中**只放标量**(int / float / bool / 短字符串)
- 长列表 / dict / 嵌套结构 → 独立模块级常量

---

## 17. 实战踩坑总结 (从 multi_factor_trend_swing 移植过程)

> 本节是从 spec → JQ 回测代码的端到端实战中**真实踩过**的坑。
> §16 偏 API 文档式的"可能出错",本节偏"实际移植时**一定**会出错的步骤"。

### 17.1 引擎环境:Python 3.6 + 行为异常 numpy

聚宽 JQBoson 引擎**不是**标准 CPython。`JQuantAPI.md` 顶部明确标注 `Python3.6 环境`。

#### 17.1.1 PEP 585 不可用 (Python 3.9+)

| 写法 | 是否可用 |
|---|---|
| `HS300_CODES: list[str] = [...]` | ❌ 抛 `TypeError: 'type' object is not subscriptable` |
| `PARAMS: dict[str, int] = {...}` | ❌ 同上 |
| `def f() -> int \| None:` (PEP 604) | ❌ 同上 |
| `f"{x=}"` debug 语法 (3.8+) | ❌ |
| `:=` walrus (3.8+) | ❌ |
| `match/case` (3.10+) | ❌ |

**症状**:
```python
TypeError: 'type' object is not subscriptable
```
通常报错的**位置不是注解所在行**,而是**该 dict/list 表达式的最后一行**(Python 内部先解析表达式再处理注解)。

**修复**:把所有 `list[str]` / `dict[str, X]` / `X | Y` 改为**无注解**:
```python
# ❌ 错
HS300_CODES: list[str] = [...]
# ✅ 对
HS300_CODES = [...]
```

如果必须保留类型注解,加 `from __future__ import annotations` 让所有注解变字符串(lazy 求值)。但本项目**未依赖任何类型注解**,无需加。

#### 17.1.2 `np.isnan(合法正数)` 误判为 `True` ⚠️ 最诡异

**症状**:
```python
>>> import numpy as np
>>> ma_10 = 28.329  # 标准 Python 浮点
>>> np.isnan(ma_10)
False  # 标准 CPython
True   # JQBoson (引擎下行为异常!)
```

标准 CPython 下 `np.isnan(任何正数)` 都是 `False`,但 **JQBoson 引擎下** `np.isnan(28.329)` 等合法正数**会返回 `True`**(可能因为 numpy 版本,或 JQ 自定义覆盖)。

**影响范围**:
- `if any(x is None or np.isnan(x) for x in [ma_10, ma_30, ma_60]):` — 对合法值也触发 `return None`
- 整个因子计算函数被静默短路
- 信号评分全部 `return 0.0` → 全市场无交易

**修复**:**用 `np.isfinite` 代替 `not np.isnan`**。

```python
# ❌ 错 (JQ 平台会误判)
if any(x is None or np.isnan(x) for x in [ma_10, ma_30, ma_60]):
    return None

# ✅ 对 (np.isfinite 在 JQ 平台行为正确, 只对 NaN/inf/-inf 返回 False)
factors = {'ma_10': ma_10, 'ma_30': ma_30, 'ma_60': ma_60, ...}
for k, v in factors.items():
    if not np.isfinite(v):
        return None
```

**原则**:在 JQ 平台**任何代码路径**遇到 `np.isnan(用户输入)` 都应警惕。**统一在函数末尾**用 `np.isfinite` 验证,不在中间路径用 `np.isnan` 短路。

#### 17.1.3 引擎实际跑出来可能与本地 Python 行为不同

**教训**:本地能跑的代码 ≠ JQ 平台能跑。关键 quirk(§16 + §17.1.2)必须在 **JQ 回测**中验证,本地无法复现。

### 17.2 `get_current_data()` 是按需加载(lazy loading),`cd.get()` 不会触发

**症状**(最常见的"无交易"原因):
```python
cd = get_current_data()
for s in stock_list:
    d = cd.get(s)        # ❌ 永远返回 None
    if d is None: continue
```
日志输出:
```
filter_universe: 退市/未上市=300 停牌=0 ST=0 数据不足=0 通过=0
```

**根因**:`JQuantAPI.md` §3 明确写:
> `get_current_data()` — 返回 dict(代码→对象), **按需获取(初始为空, 访问时加载)**

也就是说:
- `cd = get_current_data()` 返回的 dict **初始为空**
- `cd.get(s)` 不会触发 lazy loading,直接返回 `None`
- **必须用 `cd[s]` 触发加载**,或先 `set_universe(stock_list)` 预填

**修复 A (donchian 模式,用 `cd[s]`)**:
```python
try:
    d = cd[s]            # ✅ 触发 lazy loading
except KeyError:
    continue             # 股票不在 JQ 数据库 (退市/未上市)
```

**修复 B (预填,更稳)**:
```python
def initialize(context):
    set_universe(HS300_CODES_JQ)   # 预填 300 只到 cd dict
    ...
```
`set_universe()` 是为 `history()` 设默认 security_list,**但同时**也预填 `get_current_data()` 的 dict,使 `cd.get(s)` 对有效股票能正确返回。

**推荐两个一起用**:
```python
def initialize(context):
    set_universe(stock_list)       # 预填 + 设 history() 默认池

def filter_universe(raw_list, context):
    cd = get_current_data()
    for s in raw_list:
        try:
            d = cd[s]              # 触发 lazy loading (兜底)
        except KeyError:
            continue              # 真正无效的股票
```

**为什么 §16.3 推荐 `cd.get()` 是错的**:§16.3 假设 dict **已被预填**(因为有访问历史),但**首次访问** `cd.get(s)` 永远返回 `None`。**真正可靠的模式是 `cd[s] + try/except KeyError`**。

### 17.3 静态股票列表的代码转换规则

`data/config.py.HS300` 等本地列表是 **6 位纯数字**(`'000001'`, `'300750'`, `'688981'`),**不带交易所后缀**。聚宽要求带后缀(`.XSHE` / `.XSHG`)。

**规则**:
| 6 位代码开头 | 后缀 | 交易所 |
|---|---|---|
| `0` (深市主板) | `.XSHE` | 深圳 |
| `3` (深市创业板/中小) | `.XSHE` | 深圳 |
| `6` (沪市主板,含 688 科创板) | `.XSHG` | 上海 |
| `8` / `4` (北交所) | `.BJ` (少数平台) | 北京 |

**代码**:
```python
HS300_CODES_RAW = ['000001', '300750', '600519', '688981', ...]

HS300_CODES_JQ = [
    (c + '.XSHG' if c.startswith('6') else c + '.XSHE')
    for c in HS300_CODES_RAW
]
```

**注意**:
- 688 (科创板) 也用 `.XSHG`(属上交所)
- 304 (北交所) 不在 HS300 中,无需处理
- 4 / 8 开头在 HS300 / CSI1000 中也不出现

### 17.4 `attribute_history(..., skip_paused=True) + len < 60` 太严

**症状**: 静态列表 300 只 → 全部被 filter 掉。

**代码**(donchian 风格):
```python
hist = attribute_history(s, 60, '1d', ['close'], skip_paused=True, df=False, fq='pre')
if hist is None or len(hist['close']) < 60:
    continue  # 跳过
```

**根因**:`skip_paused=True` **跳过停牌日**,所以:
- 一只股过去 60 个交易日里只要有 1 天停牌 → `len(hist['close']) = 59` → 跳过
- A 股 300 只里,过去 60 个交易日有过停牌的占**大多数**

**修复**:
```python
# 1. skip_paused=False (停牌日填 NaN, 行数保证 = count)
hist = attribute_history(s, 70, '1d', ['close'], skip_paused=False, df=False, fq='pre')
if hist is None or len(hist['close']) < 60:
    continue
# 2. 只看最近 30 日是否全 NaN (排除上市未满 60 日)
recent = hist['close'][-30:]
if any(np.isnan(recent)):
    continue
```

**额外建议**:`n=70` 而非 `n=60`,留 10 日 buffer,防止边界情况。

### 17.5 "回测无交易"完整诊断 checklist

| 阶段 | 检查项 | 修复 |
|---|---|---|
| `filter_universe` | `退市/未上市=N` (N > 0 但预期不该有) | `cd.get()` → `cd[s] + try/except` + `set_universe()` |
| `filter_universe` | `停牌=N` 太多 | 区分"今日停牌"(必须跳过) vs "过去停牌日"(放宽) |
| `filter_universe` | `ST=N` 太多 | 正常,ST 真的不能买 |
| `filter_universe` | `数据不足=N` 太多 | `skip_paused=True → False` + `n=70` |
| `filter_universe` | `通过=0` 全部 300 都退市 | `cd.get()` bug,见 §17.2 |
| `calc_factors_batch` | `KeyError(history)=N` 大 | `df_close[stock]` 失败,可能 history 返回空,加 shape 日志 |
| `calc_factors_batch` | `数据不足=N` 大 | `len(close.dropna()) < 60`,改 `n=70` 或放宽到 `< 50` |
| `calc_factors_batch` | `NaN末值=N` 大 | 末日是停牌,正常跳过 |
| `calc_factors_batch` | `计算返回None=N` 大 | **`np.isnan` 误判**!改用 `np.isfinite` 末尾验证,见 §17.1.2 |
| `calc_factors_batch` | `异常=N` 大 | 拿到 `首个异常: stock=..., err=...` 直接看 |
| `entry_score` | `score=0.00` 全部 | **同 17.1.2 误判**!`if any(x is None or np.isnan(x)...)` 全 return 0.0 |
| `entry_score` | `最高 < 0.50` (评分低) | 信号过严,调 `min_entry_score` 或放宽触发条件 |
| `execute_rebalance` | `无目标持仓` 全部清仓 | 评分不足,见上一行 |

### 17.6 诊断日志模板(推荐复制粘贴)

```python
def calc_factors_batch(stock_list, context):
    log.info("  calc_factors_batch: 开始, 输入=%d 只, n=%d 天" % (len(stock_list), n))

    df_close = history(n, '1d', 'close', stock_list, df=True, skip_paused=False, fq='pre')
    if df_close is None or df_close.empty:
        log.warn("  calc_factors_batch: history() 返回空")
        return None

    # 抽样: 第一只股票的数据
    sample = list(df_close.columns)[0]
    sample_close = df_close[sample]
    log.info("  样本 %s: len=%d, 有效=%d, 末值=%s, 全 NaN=%s" %
             (sample, len(sample_close), len(sample_close.dropna()),
              sample_close.iloc[-1], sample_close.isna().all()))

    rows = {}
    n_keyerr = n_short = n_nan = n_calc_fail = n_exc = 0
    first_exc = None
    for stock in stock_list:
        try:
            close, high, low, vol = df_close[stock], df_high[stock], df_low[stock], df_vol[stock]
        except KeyError:
            n_keyerr += 1; continue
        if close is None or len(close.dropna()) < 60:
            n_short += 1; continue
        if np.isnan(close.iloc[-1]):
            n_nan += 1; continue
        try:
            d = cd[stock]
        except KeyError:
            d = None
        current_close = d.last_price if (d and d.last_price > 0) else close.iloc[-1]
        try:
            row = _calc_factors_core(close, high, low, vol, current_close, p)
            if row is not None:
                rows[stock] = row
            else:
                n_calc_fail += 1
        except Exception as e:
            n_exc += 1
            if first_exc is None: first_exc = (stock, str(e))

    log.info("  失败分类: KeyError=%d 数据不足=%d NaN=%d 计算返回None=%d 异常=%d 成功=%d" %
             (n_keyerr, n_short, n_nan, n_calc_fail, n_exc, len(rows)))
    if first_exc:
        log.warn("  首个异常: stock=%s, err=%s" % first_exc)
    return pd.DataFrame.from_dict(rows, orient='index') if rows else None
```

### 17.7 `_calc_factors_core` 推荐写法 (绕过 §17.1.2)

```python
def _calc_factors_core(close, high, low, vol, current_close, p):
    # 直接计算,不做中间 NaN 检查
    ma_10 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_30 = close.rolling(p['ma_mid']).mean().iloc[-1]
    ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]
    # ... 其他因子

    # prev_close_60 用 self != self NaN trick
    prev_close_60 = close.shift(p['mom_period']).iloc[-1]
    if prev_close_60 is None or (isinstance(prev_close_60, float) and prev_close_60 != prev_close_60) or prev_close_60 <= 0:
        return None
    mom_60 = current_close / prev_close_60 - 1

    factors = {...}
    # 末尾统一用 np.isfinite 验证
    for k, v in factors.items():
        if not np.isfinite(v):
            return None
    return factors
```

**核心原则**:
1. **不在计算中间** 用 `np.isnan(x)` 短路
2. **在计算末尾** 用 `np.isfinite(v)` 统一验证
3. 对不可避免的中间检查(如除零保护),用 `self != self` NaN trick 或 `x is None` 守护

### 17.8 静态股票池 vs `set_universe` 的取舍

| 方案 | 优点 | 缺点 |
|---|---|---|
| `get_index_stocks('000300.XSHG')` | JQ 自动维护,新调入自动包含 | 受指数调样影响,跨期结果不可比 |
| 静态 `HS300_CODES_JQ` 列表 | **跨期可比**,与本地引擎对齐 | 不随时间更新,需手动维护 |

**推荐**:用**本地静态列表**,与本地回测引擎 (`subjects/subject/backtest`) 用同一份 `data/config.py.HS300`,保证两套回测结果**股票池完全一致**。

**配 `set_universe(HS300_CODES_JQ)`** 让 `history()` 和 `get_current_data()` 都能正确返回 300 只的数据。

### 17.9 关于 `history()` vs `attribute_history()`

| 函数 | 用途 | 性能 |
|---|---|---|
| `history(N, field, security_list, df=True)` | 批量取多只股的**单字段** | 一次调用,快 |
| `attribute_history(security, N, fields, df=True)` | 取**单只股**的多字段 | 一次一只,慢 |

**性能建议**:
- **多股单字段** → `history()` 批量 (如 `df_close = history(N, '1d', 'close', stock_list, df=True)`)
- **单股多字段** → `attribute_history()` (如 `df = attribute_history(s, 70, '1d', ['open','high','low','close','volume'])`)

混合使用:`history()` 批量取 4 个字段,4 次调用;**而不是**为每只股循环 `attribute_history()`(272 × N 倍慢)。

### 17.10 完整 5+1 套防御

把上面所有坑都综合起来,**一个稳健的 JQ 策略代码应包含**:

```python
# ===== 1. initialize =====
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(...), type='stock')
    set_slippage(FixedSlippage(0.0005))
    log.set_level('order', 'error')

    # 预填 cd dict (§17.2)
    set_universe(STOCK_LIST_JQ)

    g.trade_days_set = set(get_all_trade_days().tolist())  # §16.6 守卫
    run_daily(before_market_open, '09:00')
    run_daily(market_rebalance, '14:55')
    run_daily(check_stops_daily, '15:00')

    g.params = PARAMS
    g.holdings = {}
    g.rebalance_counter = 0
    g.universe = []
    g.industry_map = {}

# ===== 2. filter_universe: skip_paused=False + cd[s] =====
def filter_universe(raw_list, context):
    cd = get_current_data()
    n_total = len(raw_list)
    n_none = n_paused = n_st = n_data = 0
    out = []
    for s in raw_list:
        try:
            d = cd[s]              # ✅ 触发 lazy loading
        except KeyError:
            n_none += 1; continue
        if d.paused:
            n_paused += 1; continue
        if d.is_st:
            n_st += 1; continue
        try:
            hist = attribute_history(s, 70, '1d', ['close'],
                                       skip_paused=False, df=False, fq='pre')  # ✅ §17.4
        except Exception:
            n_data += 1; continue
        if hist is None or len(hist['close']) < 60:
            n_data += 1; continue
        recent = hist['close'][-30:]
        if any(np.isnan(recent)):
            n_data += 1; continue
        out.append(s)
    log.info("  filter_universe: 原始=%d 退市=%d 停牌=%d ST=%d 数据=%d 通过=%d" %
             (n_total, n_none, n_paused, n_st, n_data, len(out)))
    return out

# ===== 3. _calc_factors_core: 末尾 np.isfinite 验证 (§17.1.2) =====
def _calc_factors_core(close, high, low, vol, current_close, p):
    ma_10 = close.rolling(p['ma_short']).mean().iloc[-1]
    ma_30 = close.rolling(p['ma_mid']).mean().iloc[-1]
    ma_60 = close.rolling(p['ma_long']).mean().iloc[-1]
    atr_14 = ...
    rsi_14 = ...
    prev_close_60 = close.shift(p['mom_period']).iloc[-1]
    if prev_close_60 is None or prev_close_60 != prev_close_60 or prev_close_60 <= 0:
        return None
    mom_60 = current_close / prev_close_60 - 1

    factors = {'close': float(current_close), 'ma_10': float(ma_10), ...}
    for k, v in factors.items():
        if not np.isfinite(v):
            return None
    return factors

# ===== 4. entry_score: 不在中间用 np.isnan =====
def entry_score(f, p):
    score = 0.0
    for k in ['close', 'ma_10', 'ma_30', 'ma_60', 'atr_14',
              'volume_ratio_20', 'mom_60', 'rsi_14']:
        if f.get(k) is None:
            return 0.0
    close = f['close']
    if close <= 0:
        return 0.0
    # ... 5 个 if 加分 ...
    return score

# ===== 5. 交易: cd[s] + 科创板限价单 =====
for stock, value in target_weights.items():
    try:
        d = cd[stock]              # ✅ 触发 lazy loading
    except KeyError:
        continue
    if d.paused: continue
    if d.high_limit > 0 and d.last_price >= d.high_limit: continue  # ✅ §16.5
    last_price = d.last_price
    if last_price <= 0 or np.isnan(last_price): continue
    lot_size = 200 if stock.startswith('688') else 100  # ✅ §16.8
    ...
    if stock.startswith('688'):
        order(stock, delta, LimitOrderStyle(min(last_price * 1.005, 9999.99)))
    else:
        order(stock, delta)        # ✅ §16.9
```

**这套模板**已经把 §16 + §17 全部 14 个 quirk 综合覆盖。可以直接作为新策略移植的起点。

### 17.11 给移植新策略的检查表

移植新策略时,按这个顺序检查:

1. **Python 3.6 兼容**:所有 `list[X]` / `X | Y` 改为无注解或加 `from __future__ import annotations`
2. **cd 预填**:`initialize()` 加 `set_universe(stock_list)`,**所有** `cd.get(s)` 改 `cd[s] + try/except KeyError`
3. **历史过滤**:`attribute_history(skip_paused=True) + len < N` 改 `skip_paused=False + n=N+10 + 检查最近 30 日`
4. **因子计算**:`_calc_factors_core` 末尾用 `np.isfinite` 统一验证,**不在中间用 `np.isnan` 短路**
5. **信号评分**:`entry_score` 不检查 `np.isnan`,只检查 `None` 和 `close <= 0`
6. **下单**:
   - 科创板(688) → `LimitOrderStyle(price * 1.005)`
   - 主板 → `order(stock, delta_shares)` 不用 `order_target_value`
7. **filters**:所有 `d.high_limit/low_limit` 比较前加 `> 0` 守护
8. **PARAMS**:长列表放模块级常量,**不**放 `g.params`
9. **回测期守卫**:`run_daily` 入口加 `_is_trading_day()` 守卫(模拟盘准备)
10. **诊断**:第一版加完整 `filter_universe` / `calc_factors_batch` / `entry_score` 诊断日志,先跑一次确认全流程无静默失败

跑出 0 笔交易时,按 §17.5 checklist 逐项定位。

### 17.12 ⚠️ `template_trend_momentum_strategy_1.py` 只是参考,不是模板

> **本节是 2026-06 从 `multi_factor_trend_swing` 移植中得到的惨痛教训**。
> `createBase/template_trend_momentum_strategy_1.py` 是**已对齐的标杆实现**,但它是**为 trend_momentum_strategy_1 这一个策略设计的**,有大量该策略特有的元素。**严禁**把它当"通用模板"逐章套用到其他策略。

#### 17.12.1 模板里哪些是"通用约定"可以借,哪些是"策略特有"必须改

| 类别 | 是否可借 | 原因 |
|---|---|---|
| `from jqdata import *` 后的 `_sum/_max/_min` 别名 | ✅ 可借 | 聚宽环境通用 |
| `run_daily(daily_handle, time="09:30")` 单一调度 | ✅ 可借 | T-1 严格无前视约定 |
| `g.bar_index` 累加 + `if bar_idx == 1: return` | ✅ 可借 | 与本地 runner 对齐 |
| `enforce_max_single_weight` / `enforce_industry_concentration` / `enforce_max_turnover` | ✅ 可借 | 通用 5 仓位约束 |
| `fill_cash_with_remaining_candidates` | ✅ 可借 | 通用现金沉淀填补 |
| 09:30 时 `cd.paused / cd.is_st` 不可靠 | ✅ 可借 | 平台特性 |
| `attribute_history(..., fq="pre")` 显式前复权 | ✅ 可借 | 平台特性 |
| **docstring 措辞** (如"多指标共振趋势策略") | ❌ **必须改** | 每个策略的"策略定位"不同 |
| **FIXED_UNIVERSE = HS300 + CYB_STAR_50 (356 只)** | ⚠️ **按 spec 决定** | 模板用的是 trend_momentum 的 universe, 其他策略可能用 HS300 单独 / 动态池 / 完全不同的列表 |
| **入场信号 1 个 (单 AND 触发)** | ❌ **必须改** | multi_factor_trend_swing 是 5 信号加权,ma_cross 是单信号金叉,donchian 是突破,每个策略入场结构都不同 |
| **出场信号 5 个 + weight 排序** | ⚠️ **按 spec 决定** | 信号名 / 触发条件 / weight 都来自 spec,模板里的具体值不能照抄 |
| **PARAMS 字段** (target_holdings / max_single / max_industry / max_turnover / 因子窗口 / 阈值) | ❌ **必须改** | 完全策略特定 |
| **holding_days 起始值 0 vs 1** | ⚠️ **按本地 P3 修复** | 见 §17.12.3 |

#### 17.12.2 套模板破坏策略本意的 3 个真实案例 (从 multi_factor_trend_swing 移植中学到)

**案例 1: universe 错位**
- spec 写 `test_universe: HS300`,实际意图是 HS300 单独
- 模板的 `FIXED_UNIVERSE` 是 HS300 + CYB_STAR_50 (356 只), 直接套用会把**多出 56 只**非 spec 标的进候选池
- 后果:科创板 200 股规则被无意识触发,引入 spec 没说过的交易成本,回测结果与本地 runner 不一致
- **正确做法**:从 `D:\project\quant\my-quant3\data\config.py` 取 `HS300` 单独或 `["HS300", "CYB_STAR_50"]`,看 spec 怎么写

**案例 2: exit_weights 多余信号**
- spec 5 个出场信号,模板的 `exit_weights` 有 5 个键
- 但"按优先级凑齐"时会无意识塞一个 spec 里没有的占位信号(如 `atr_filter_exit`)
- 后果:`should_exit` 优先级链条凭空插一档,触发分布错位
- **正确做法**:`should_exit` 的 `_check_exit_signal` 实现必须严格按 spec 的 5 个 (或 N 个) 信号,一个不多一个不少

**案例 3: 策略本质差异被"形似"掩盖**
- trend_momentum 是"7×40% 集中",spec 是"12×10% 高分散"
- 即使 PARAMS 数字对了,章节 docstring 还在说"等权 1/7,cap 到 40%",没体现"12×10% 等权起步后被三约束链压"的真实意图
- 后果:后人读代码理解策略时,会被章节 docstring 误导
- **正确做法**:每个章节 docstring 写这个**当前策略**的语义,不是模板的通用描述

#### 17.12.3 holding_days 起始值的"对齐陷阱"

这是最隐蔽的偏差,容易在"以为对齐了"时翻车:

| 本地 runner (P3 修复后) | 模板 (旧版习惯) | 后果 |
|---|---|---|
| `buy()` 设 `hd=1` (1-based) | `buy()` 设 `hd=0` (0-based) | time_stop 晚 1 天触发 |
| 第 1 个交易日 end-of-day: `hd=1` | 第 1 个交易日 step 1 后: `hd=1` | (同) |
| 第 N 个交易日 end-of-day: `hd=1+(N-1)=N` | 第 N 个交易日 step 1 后: `hd=0+N=N` | (同) |
| **time_stop (max=45) 触发: buy 日 + 44** | **time_stop 触发: buy 日 + 45** | **差 1 个交易日** |

模板沿用了"旧版 hd=0 + step 1 +=1"的写法,看起来"也对",但**与本地 P3 修复后的 `buy()` 直接设 `hd=1` 不一致**。time_stop 是按"实际持有天数"设计的,晚 1 天会显著影响 time_stop 触发频次,长期累积影响年化收益和胜率。

**正确做法**:`_execute_buy` 中显式设 `"holding_days": 1`,并在 docstring 写明"对齐本地 P3 修复 (subjects/subject/backtest/portfolio.py:142)"。

#### 17.12.4 正确的移植流程

```text
1. 读 spec 完整 (final.md + narrative)
   ↓
2. 提炼策略本质:
   - 策略类型 (动量 / 波段 / 反转 / 套利)
   - universe (固定 / 动态 / 混合)
   - 入场结构 (单 AND / 多信号加权 / score 排名)
   - 持仓周期 (短期 / 中期 / 长期)
   - 调仓频率 + 5 仓位约束参数
   ↓
3. 从模板只借"通用约定" (见 17.12.1 表的 ✅ 行)
   ↓
4. 重新设计章节 docstring 体现"当前策略"语义
   ↓
5. 严格按 spec 实现:
   - 因子 (数量 / 窗口 / 计算公式)  ← 改
   - 入场信号 (名称 / 触发 / 权重)  ← 改
   - 出场信号 (名称 / 触发 / 权重)  ← 改
   - PARAMS 全部字段  ← 改
   - universe  ← 改
   ↓
6. 对照 `createBase/weight-rules.md` 走 9.x checklist
   ↓
7. 跑 self_check() 确认 PARAMS 必填字段 + spec 调优值
   ↓
8. 跑本地 runner 与 JQ 脚本,对比首日 / 首次 rebalance / 出场分布
```

#### 17.12.5 反例: "复制模板 → 改 4 个数字 → 上线"

这是**最高频的错误**。具体症状:

- ✅ 11 章节结构对
- ✅ 5 仓位约束函数对
- ✅ 9:30 单一调度对
- ❌ docstring 还说"多指标共振趋势策略"(trend_momentum 特有)
- ❌ `FIXED_UNIVERSE` 还是 356 只
- ❌ `entry_score` 还是单信号 AND
- ❌ `exit_weights` 多了一个 spec 没有的占位
- ❌ `holding_days` 还是 0 (与本地 P3 修复不一致)
- ❌ 章节 docstring 描述的是"7×40% 集中"语义,不是当前策略的"12×10% 高分散"

跑出来回测结果**与本地 runner 偏差 5-15%**,但排查时每个章节"看起来都对",不知道哪里出了问题。

**教训**:每个策略的 JQ 脚本应该是**该策略的独立实现**,不是"模板的派生"。

#### 17.12.6 跨文档引用

| 文档 | 用途 |
|---|---|
| `createBase/weight-rules.md` §5.1 | holding_days 1-based 详细说明 + P3 修复背景 |
| `createBase/weight-rules.md` §1.3 | bar_idx 1-based 详细说明 + 修正 `should_rebalance` docstring 误导 |
| `createBase/weight-rules.md` §6.3 | `can_buy/sell_at_open` 涨停/跌停判断 + 卖跌停废单问题 |
| `joinQuant/RULES.md` §3 | "新策略存放" + 章节命名 + "只改 1/3/4/5 章节"的边界 |

> **一句话原则**:`template_*.py` 是"已对齐的标杆实现",`weight-rules.md` 是"对接规范",`JQuantAPI.md` 是"API + 实战坑"。三者**互为补充**,但**不能互相替代**。移植新策略时,**spec 是主,模板是辅,规则文档是底线**。

