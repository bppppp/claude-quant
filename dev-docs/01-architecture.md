# 01 - 整体架构设计

## 1.1 系统目标

实现 ATOS（Adaptive Trend-Oscillation Strategy）量化交易系统的完整工程化，覆盖：

- 离线回测（2016-2025 全 A 股）
- 半自动实盘（每日 T+1 决策、信号推送）
- 实时监控（净值、回撤、状态、告警）

## 1.2 架构分层

### 1.2.1 七层架构（含预计算层）

```
┌────────────────────────────────────────────────────────────┐
│ L7  应用层     main.py / CLI / Streamlit 看板 / 报告生成      │
├────────────────────────────────────────────────────────────┤
│ L6  决策层     组合管理 + 订单执行 + 风控                        │
├────────────────────────────────────────────────────────────┤
│ L5  信号层     6 买点 + 4 卖点 + 假突破过滤                    │
├────────────────────────────────────────────────────────────┤
│ L4  选股层     12 因子 + 预处理 + 合成 + 动态权重              │
├────────────────────────────────────────────────────────────┤
│ L3  状态层     4 状态分类 + 迟滞 + 震荡下行叠加                 │
├────────────────────────────────────────────────────────────┤
│ L2  指标层     13 个技术指标（MA/MACD/KDJ/...）               │
├────────────────────────────────────────────────────────────┤
│ L1  预计算层    增量计算 + 缓存 + 原子写 + 校验（v7.0 新增）│
├────────────────────────────────────────────────────────────┤
│ L0  数据层     原始 K 线 + 复权 + 清洗 + 存储                  │
└────────────────────────────────────────────────────────────┘

L1 预计算层作用：
- 每日盘后增量计算所有指标/因子/状态
- 缓存到 data/processed/v1/（Parquet 格式）
- 运行时只读取缓存（< 5ms / 只）
- 性能提升：完整回测从 30 分钟 → 5 分钟（6x）
```

### 1.2.2 层间接口

每层只暴露**输入/输出**，不暴露内部实现：

```python
# L0 → L1
def load_ohlcv(symbol: str, start: str, end: str) -> pd.DataFrame:
    # 返回: columns = [date, open, high, low, close, volume]
    pass

# L1 → L2
def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    # 返回: df + [MA5, MA10, MA20, MACD, KDJ, RSI, BOLL, ATR, ...]
    pass

# L2 → L3
def detect_regime(df: pd.DataFrame) -> pd.Series:
    # 返回: index=date, values in {BULL, SIDEWAYS, BEAR, CRASH}
    pass

# L3 → L4
def select_stocks(factor_df: pd.DataFrame, regime: str, top_n: int) -> list[str]:
    # 返回: 选中的股票代码列表
    pass

# L4 → L5
def generate_signals(df: pd.DataFrame, regime: str) -> dict:
    # 返回: {"buy": [...], "sell": [...]}
    pass

# L5 → L6
def check_risk(position, current_price, regime) -> tuple[bool, float, str]:
    # 返回: (是否卖出, 卖出比例, 原因)
    pass
```

## 1.3 数据流

### 1.3.1 回测数据流

```
原始数据
   ↓
[数据层] 加载 + 复权 + 清洗
   ↓
[指标层] 计算所有技术指标
   ↓
[状态层] 4 状态分类 + 迟滞 + 震荡下行
   ↓
[选股层] 12 因子 → 合成 → Top N
   ↓
[信号层] 生成买点信号
   ↓
[风控层] 检查买入条件（仓位、冷却、状态）
   ↓
[执行层] 模拟下单
   ↓
[回测引擎] 逐日循环
   ↓
[绩效] 计算 Sharpe、回撤等
```

### 1.3.2 实盘数据流

```
T 日收盘
   ↓
拉取当日全市场 K 线（15:30 后）
   ↓
计算指标 + 状态 + 选股 + 信号
   ↓
生成次日交易计划（买入/卖出清单）
   ↓
T+1 日开盘前推送（钉钉/微信）
   ↓
人工确认 / 自动执行
   ↓
T+1 收盘后记录成交
   ↓
更新持仓 / 计算净值 / 触发告警
```

## 1.4 模块依赖

```
config  ← 所有层
data    ← indicators
indicators ← regime, selection, signals
regime  ← selection, signals
selection ← signals
signals ← risk
risk    ← execution
backtest ← all
monitoring ← execution, backtest
```

依赖原则：
- **同层不互相依赖**（如 signals 不调用 selection）
- **下层不知道上层存在**（如 indicators 不引用 regime）
- **config 被所有层引用**（统一配置入口）

## 1.5 核心抽象

### 1.5.1 抽象基类

```python
from abc import ABC, abstractmethod

class BaseIndicator(ABC):
    """技术指标抽象"""
    @abstractmethod
    def calc(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

class BaseRegime(ABC):
    """市场状态识别抽象"""
    @abstractmethod
    def detect(self, df: pd.DataFrame) -> pd.Series:
        pass

class BaseSignal(ABC):
    """买卖信号抽象"""
    @abstractmethod
    def generate(self, df: pd.DataFrame, regime: str) -> pd.Series:
        pass
```

### 1.5.2 上下文对象

```python
@dataclass
class TradingContext:
    """交易上下文（贯穿各层）"""
    date: pd.Timestamp
    regime: str                          # 当前状态
    choppy_bear: bool                    # 震荡下行标志
    positions: dict[str, Position]       # 当前持仓
    target_pos: dict[str, float]         # 目标仓位
    cash: float
    equity: float
    config: StrategyConfig
```

## 1.6 并发与性能

### 1.6.1 回测性能

- 10 年 × 5000 只股票 = 5000 万行
- 串行：~2 小时
- 并行（Dask）：~10 分钟

```python
# Dask 并行回测示例
import dask.dataframe as dd

def parallel_backtest(stock_list, config):
    delayed_results = []
    for symbol in stock_list:
        delayed_results.append(dask.delayed(run_single_backtest)(symbol, config))
    results = dask.compute(*delayed_results)
    return aggregate_results(results)
```

### 1.6.2 实盘性能

- 每日 T+1 决策时间：< 5 分钟
- 全市场扫描：< 2 分钟
- 满足日常使用

## 1.7 错误处理

### 1.7.1 错误分类

| 级别 | 类型 | 处理 |
|---|---|---|
| L0 | 数据缺失 | 跳过该股票、记录日志 |
| L1 | 指标计算异常 | 标记 NaN、跳过该日 |
| L2 | 状态识别异常 | 保持上一状态 |
| L3 | 选股异常 | 退回到等权合成 |
| L4 | 信号异常 | 不开新仓 |
| L5 | 执行异常 | 重试 3 次、失败告警 |

### 1.7.2 日志规范

```python
import logging

# 分级日志
logger = logging.getLogger("atos")
logger.setLevel(logging.INFO)

# 关键事件必须记录
logger.info("REGIME_CHANGE: %s → %s", old, new)
logger.warning("CHOPPY_BEAR_TRIGGERED: cum_ret=%.2f%%, vol=%.2f%%", ...)
logger.error("DATA_MISSING: %s", symbol)
```

## 1.8 可测试性

### 1.8.1 测试金字塔

```
       /      /  \         E2E 测试（端到端）
     /────\        集成测试
    /──────\       单元测试（最多）
   /────────```

### 1.8.2 关键测试用例

```python
# test_regime.py
def test_bull_state_detection():
    """牛市状态应正确识别"""
    df = create_bull_market_data()
    regime = detect_regime(df)
    assert regime.iloc[-1] == "BULL"

def test_choppy_bear_detection():
    """震荡下行应正确触发"""
    df = create_choppy_bear_data()
    cb = detect_choppy_bear(df)
    assert cb["is_choppy_bear"] == True

def test_regime_hysteresis():
    """状态迟滞：连续 3 日才切换"""
    df = create_flapping_market_data()
    regime = detect_regime_with_hysteresis(df)
    # 不应频繁切换
    assert (regime != regime.shift(1)).sum() <= 3
```

## 1.9 扩展性

### 1.9.1 未来扩展点

| 扩展 | 接口预留 |
|---|---|
| 增加新指标 | 继承 `BaseIndicator` |
| 增加新状态 | 修改 `BaseRegime.detect()` |
| 增加新因子 | 继承 `BaseFactor` |
| 增加新信号 | 继承 `BaseSignal` |
| 多标的组合 | 修改 `Portfolio` |

### 1.9.2 配置化

所有可扩展点通过配置启用/禁用：

```yaml
# config/params.yaml
indicators:
  enable: [ma, macd, kdj, rsi, boll, atr, dmi, dc, obv, mfi, vwap, cci]
  disable: []

regimes:
  enable: [BULL, SIDEWAYS, BEAR, CRASH]
  custom: {}

signals:
  buy:
    enable: [ma_macd, kdj_rsi, boll_vol, dc_break, macd_div, ma_conv]
  sell:
    enable: [ma_macd, kdj_over, boll_mid, macd_top]
```

## 1.10 部署架构

```
┌─────────────────┐
│   调度系统       │  cron / Airflow
│  (每日 17:00)    │
└────────┬────────┘
         ↓
┌─────────────────┐
│  数据拉取        │  akshare / baostock
│  (17:00-17:30)   │
└────────┬────────┘
         ↓
┌─────────────────┐
│  信号计算        │  ATOS 主程序
│  (17:30-18:00)   │
└────────┬────────┘
         ↓
┌─────────────────┐
│  报告推送        │  钉钉 / 飞书 / 邮件
│  (18:00-18:30)   │
└────────┬────────┘
         ↓
┌─────────────────┐
│  监控看板        │  Streamlit (24/7)
│  (实时)          │
└─────────────────┘
```

## 1.11 总结

| 设计原则 | 体现 |
|---|---|
| 分层解耦 | 6 层架构 + 抽象基类 |
| 配置驱动 | StrategyConfig + YAML |
| 状态优先 | 状态层先于一切决策 |
| 移动止盈 | 风控层默认机制 |
| 冷却防抖 | CooldownManager |
| 可测试性 | 测试金字塔 + 关键测试 |
| 可扩展性 | 接口预留 + 配置化 |
| 错误处理 | 分级日志 + 降级策略 |
