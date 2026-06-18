# 11 - 开发指南

## 11.1 目标

指导开发者**规范地**实现、测试、调试、上线 ATOS 策略。

## 11.2 开发环境

### 11.2.1 必备工具

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | 3.10+ | 主语言 |
| Git | 2.30+ | 版本控制 |
| VSCode / PyCharm | 最新 | IDE |
| pytest | 7.0+ | 单元测试 |
| black | 23.0+ | 代码格式化 |
| flake8 | 6.0+ | 代码检查 |
| mypy | 1.0+ | 类型检查 |

### 11.2.2 依赖安装

```bash
# 克隆代码
git clone <repo_url>
cd atos

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt
```

```txt
# requirements.txt（修复 C28: 补全依赖）
pandas>=1.5.0
numpy>=1.20.0
akshare>=1.12.0
baostock>=0.8.9
pyarrow>=10.0.0
streamlit>=1.20.0
requests>=2.28.0
pyyaml>=6.0
statsmodels>=0.13.0
psutil>=5.9.0         # 修复 C28: 预计算并行用
schedule>=1.2.0      # 调度（10-deployment）
ipython>=8.0.0       # 修复 C28: Jupyter 调试
```

```txt
# requirements-dev.txt
-r requirements.txt
pytest>=7.0
pytest-cov>=4.0
black>=23.0
flake8>=6.0
mypy>=1.0
ipython>=8.0
```

## 11.3 代码规范

### 11.3.1 PEP 8

- 缩进：4 空格
- 行长：≤ 100 字符
- 命名：
  - 类：`PascalCase`
  - 函数/变量：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`
  - 私有：`_` 前缀

### 11.3.2 类型注解

```python
from typing import Optional, Union
import pandas as pd
import numpy as np


def calc_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """计算 ATR

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        period: 周期，默认 14

    Returns:
        ATR 序列
    """
    ...


def detect_regime(
    df: pd.DataFrame,
    config: "StrategyConfig",
    threshold: Optional[float] = None
) -> pd.Series:
    """检测市场状态"""
    ...
```

### 11.3.3 Docstring（Google 风格）

```python
def example_function(param1: int, param2: str) -> bool:
    """简短描述（一行）

    详细描述（可选）。

    Args:
        param1: 参数 1 描述
        param2: 参数 2 描述

    Returns:
        返回值描述

    Raises:
        ValueError: 触发条件

    Example:
        >>> example_function(1, "test")
        True
    """
    ...
```

### 11.3.4 命名约定

```python
# 文件：snake_case
data_loader.py
market_regime.py

# 类：PascalCase
class PositionManager:
    pass

# 函数：snake_case，动词开头
def calc_ma(): ...
def detect_regime(): ...
def generate_signals(): ...

# 变量：snake_case
df_kdj = ...
regime = ...

# 常量：UPPER_SNAKE_CASE
MAX_POSITION = 0.95
DEFAULT_PERIOD = 20

# 私有：_ 前缀
def _internal_helper():
    pass
```

## 11.4 Git 工作流

### 11.4.1 分支策略

```
main (稳定)
  │
  ├── develop (开发)
  │     │
  │     ├── feature/regime-detection
  │     ├── feature/buy-signals
  │     └── feature/backtest-engine
  │
  ├── release/v1.0
  │
  └── hotfix/critical-bug
```

### 11.4.2 提交规范（Conventional Commits）

```
feat: 添加震荡下行检测
fix: 修复 ATR 计算 NaN 问题
docs: 更新 README
style: 格式化代码（black）
refactor: 重构 PositionManager
test: 添加状态识别测试
chore: 更新依赖
```

### 11.4.3 提交模板

```bash
# .gitmessage
# <type>(<scope>): <subject>
#
# <body>
#
# <footer>

# 例：
# feat(regime): 添加 4 状态识别
#
# - 实现 BULL / SIDEWAYS / BEAR / CRASH 分类
# - 加入迟滞机制（连续 3 日 + 5 日冷却）
# - 单元测试覆盖率 90%+
```

## 11.5 测试规范

### 11.5.1 测试金字塔

```
       /\
      /E2E\        端到端测试（少）
     /─────\
    /集成测试\      集成测试（中）
   /─────────\
  /  单元测试  \    单元测试（多）
 /──────────────\
```

### 11.5.2 单元测试

```python
# tests/test_indicators.py
import pytest
import pandas as pd
import numpy as np
from indicators.trend import calc_ma


def test_calc_ma_with_default_periods():
    """默认周期应包含 5/10/20/60/120/250"""
    close = pd.Series(np.arange(300, dtype=float))
    result = calc_ma(close)
    assert set(result.columns) == {"MA5", "MA10", "MA20", "MA60", "MA120", "MA250"}


def test_calc_ma_5_day_average():
    """MA5 应为最近 5 日的均值"""
    close = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    result = calc_ma(close, periods=[5])
    assert result["MA5"].iloc[4] == 3.0  # (1+2+3+4+5)/5
    assert result["MA5"].iloc[-1] == 8.0  # (6+7+8+9+10)/5


def test_calc_ma_handles_nan_at_start():
    """数据不足时应有 NaN"""
    close = pd.Series([1, 2, 3], dtype=float)
    result = calc_ma(close, periods=[5])
    assert result["MA5"].iloc[0] == 1.0  # min_periods=1
```

### 11.5.3 Fixtures

```python
# tests/conftest.py
import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def bull_market_data():
    """牛市数据 fixture"""
    np.random.seed(42)
    n = 500
    close = pd.Series(
        np.cumsum(np.random.randn(n) * 0.5) + 3000,
        index=pd.date_range("2020-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close + np.abs(np.random.randn(n)),
        "low": close - np.abs(np.random.randn(n)),
        "close": close,
        "volume": np.random.randint(1e8, 1e9, n)
    })


@pytest.fixture
def choppy_bear_data():
    """震荡下行数据 fixture"""
    np.random.seed(123)
    n = 500
    close = pd.Series(
        3000 + np.linspace(-200, 0, n) + np.random.randn(n) * 0.3,
        index=pd.date_range("2020-01-01", periods=n)
    )
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.random.randint(1e8, 1e9, n)
    })


@pytest.fixture
def config():
    from config.strategy_config import StrategyConfig
    return StrategyConfig()
```

### 11.5.4 集成测试

```python
# tests/test_integration.py
def test_full_backtest_workflow(bull_market_data, config):
    """完整回测流程"""
    from indicators.pipeline import calc_all_indicators
    from backtest.engine import BacktestEngine

    df = calc_all_indicators(bull_market_data)
    engine = BacktestEngine(config)
    result = engine.run(df)

    assert result.equity_curve is not None
    assert result.metrics["annual_return"] > 0  # 牛市应赚钱
```

### 11.5.5 覆盖率要求

```bash
# 运行测试并生成覆盖率
pytest --cov=atos --cov-report=html

# 目标
- 核心模块（indicators, regime, signals, risk）：≥ 90%
- 工具模块：≥ 70%
- 总覆盖率：≥ 80%
```

### 11.5.6 Mock 与 Stub

```python
from unittest.mock import Mock, patch


def test_position_manager_with_mock():
    """使用 mock 测试"""
    pm = PositionManager()
    pos = Mock(spec=Position)
    pos.symbol = "000001"
    pm.add(pos)
    assert "000001" in pm.positions


def test_cooldown_with_time():
    """冷却期时间测试（修复 C29: 移除无效的 mock）"""
    # 修复 C29: CooldownManager 不再调用 pd.Timestamp.now()（已用参数注入）
    # 直接用真实时间测试
    cd = CooldownManager()
    exit_date = pd.Timestamp("2024-01-01")
    cd.record_exit("000001", exit_date, is_failure=True)
    # 冷却期内不能买
    can_buy, reason = cd.can_buy("000001", exit_date + pd.Timedelta(days=2), "BULL")
    assert can_buy == False
    # 5 日后可以买
    can_buy, reason = cd.can_buy("000001", exit_date + pd.Timedelta(days=6), "BULL")
    assert can_buy == True
```

## 11.6 调试技巧

### 11.6.1 日志

```python
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/atos.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("atos")

# 使用
logger.info("Starting backtest...")
logger.warning("Data missing for 000001")
logger.error("Backtest failed", exc_info=True)
```

### 11.6.2 性能分析

```python
# cProfile
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# 运行回测
result = engine.run(df)

profiler.disable()
stats = pstats.Stats(profiler).sort_stats("cumulative")
stats.print_stats(20)
```

### 11.6.3 Jupyter 调试

```python
# 在 Jupyter 中逐步调试
df = calc_all_indicators(df)
# 暂停，看中间结果
import pdb; pdb.set_trace()

regime = detect_full_regime(df, config)
```

### 11.6.4 常见 Bug

| Bug | 原因 | 解决 |
|---|---|---|
| NaN 蔓延 | 早期数据不足 | `min_periods=1` |
| 索引错位 | `shift(1)` vs `shift(-1)` | 注意方向 |
| 未来函数 | 用了未来数据 | 检查 `shift` 方向 |
| 除零错误 | 极端值 | `+ 1e-9` |
| 内存爆炸 | 全市场加载 | 分批处理 |

## 11.7 上线流程

### 11.7.1 阶段

```
开发 (dev) → 单元测试 → 集成测试 → 回测验证 → 模拟盘 → 小资金实盘 → 全资金实盘
```

### 11.7.2 上线检查清单

```
[ ] 1. 所有单元测试通过
[ ] 2. 回测指标达标（年化 ≥ 15%, 回撤 ≤ 15%, 夏普 ≥ 1.2）
[ ] 3. Walk-Forward 验证通过
[ ] 4. 参数扰动测试：脆弱参数已加固
[ ] 5. 关键年份分析：2018/2020/2022/2024 无重大问题
[ ] 6. 模拟盘 1 个月无异常
[ ] 7. 数据获取正常
[ ] 8. 告警系统正常
[ ] 9. 监控看板可访问
[ ] 10. 应急联系人就位
[ ] 11. 资金管理保护就位
[ ] 12. 法律合规检查通过
```

### 11.7.3 回滚预案

```bash
# scripts/rollback.sh
#!/bin/bash
# 紧急回滚到上一版本
git checkout HEAD~1
systemctl restart atos
echo "Rolled back to $(git log -1 --oneline)"
```

## 11.8 性能优化

### 11.8.1 常见瓶颈

| 瓶颈 | 优化 |
|---|---|
| 因子计算 | 缓存到磁盘 |
| 横截面标准化 | 预计算 |
| 信号计算 | 向量化 |
| 回测循环 | 减少 for 循环 |
| 数据加载 | 内存缓存 |

### 11.8.2 并行化

```python
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


def parallel_backtest(stock_list, config):
    """并行回测多只股票"""
    with ProcessPoolExecutor(max_workers=mp.cpu_count()) as executor:
        results = list(executor.map(
            lambda sym: run_single_backtest(sym, config),
            stock_list
        ))
    return aggregate_results(results)
```

### 11.8.3 内存管理

```python
# 显式删除大数据
del big_df
import gc
gc.collect()

# 分块处理
for chunk in pd.read_csv("huge.csv", chunksize=10000):
    process(chunk)
```

## 11.9 文档与注释

### 11.9.1 README 模板

```markdown
# ATOS - Adaptive Trend-Oscillation Strategy

## 简介
基于 4 状态识别的 A 股做多策略

## 快速开始
```bash
pip install -r requirements.txt
python scripts/daily_signal.sh
```

## 项目结构
...

## 回测
```bash
python run_backtest.py
```

## 文档
详细文档见 dev-docs/

## 免责声明
本项目仅供研究，不构成投资建议
```

### 11.9.2 代码注释

```python
# 清晰的注释
# 1. 解释"为什么"（不是"是什么"）
# 2. 标注关键算法
# 3. 解释复杂的业务逻辑

def calc_atr(high, low, close, period=14):
    """使用 Wilder 平滑（不是普通 SMA）"""
    # Wilder 平滑的 alpha = 1/period，比 EMA 更平滑
    return ...
```

## 11.10 安全与合规

### 11.10.1 数据安全

- 配置文件不提交（用 .gitignore）
- API token 用环境变量
- 数据库密码加密

```bash
# .gitignore
config/local.yaml
.env
data/
logs/
```

### 11.10.2 合规清单

- [ ] 数据来源合规
- [ ] 不涉及内幕信息
- [ ] 不操纵市场
- [ ] 风险揭示完整
- [ ] 用户协议完备

## 11.11 预计算系统测试（衔接 12-precompute.md）

### 11.11.1 预计算核心测试

```python
# tests/test_precompute_core.py
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from precompute.incremental import IncrementalUpdater
from precompute.parallel import ParallelPrecomputer
from precompute.cache import LRUCache


def test_lru_cache_basic():
    """LRU 缓存基本功能"""
    cache = LRUCache(max_size=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") == 1
    cache.put("d", 4)  # 触发淘汰
    assert cache.get("b") is None  # b 被淘汰
    assert cache.get("c") == 3
    assert cache.get("d") == 4


def test_lru_cache_hit_rate():
    """LRU 命中率统计"""
    cache = LRUCache(max_size=10)
    for i in range(10):
        cache.put(f"k{i}", i)
    for i in range(10):  # 全部命中
        cache.get(f"k{i}")
    stats = cache.stats()
    assert stats["hit_rate"] == 1.0
    assert stats["hits"] == 10


def test_incremental_update_first_time():
    """首次预计算：全量"""
    updater = IncrementalUpdater(config=test_config)
    result = updater.update_symbol("000001")
    assert Path("data/processed/v1/stock/000001.parquet").exists()
    assert result["new_rows"] > 0


def test_incremental_update_idempotent():
    """重复预计算应幂等（无新数据时跳过）"""
    updater = IncrementalUpdater(config=test_config)
    updater.update_symbol("000001")
    first_mtime = Path("data/processed/v1/stock/000001.parquet").stat().st_mtime

    result = updater.update_symbol("000001")
    assert result["new_rows"] == 0  # 无新数据


def test_parallel_precompute_uses_workers():
    """并行预计算应使用多 worker"""
    parallel = ParallelPrecomputer(config=test_config)
    assert parallel.n_workers >= 1
    assert parallel.n_workers <= os.cpu_count()


def test_atomic_write_no_leftover_files():
    """原子写入：失败不应产生临时文件"""
    from precompute.resilience import atomic_write

    # 模拟写入失败
    with mock.patch("pandas.DataFrame.to_parquet", side_effect=IOError):
        with pytest.raises(IOError):
            atomic_write(test_df, Path("/tmp/test_atomic.parquet"))

    # 不应有临时文件残留
    assert not Path("/tmp/test_atomic.parquet.tmp").exists()
```

### 11.11.2 缓存性能基准测试

```python
# tests/benchmarks/test_precompute_perf.py
import pytest
import time
from precompute.incremental import IncrementalUpdater


def test_cache_read_speed():
    """缓存读取应 < 10ms"""
    updater = IncrementalUpdater(config=test_config)
    updater.update_symbol("000001")

    start = time.perf_counter()
    for _ in range(100):
        df = updater.load_processed("000001", date="2024-01-02")
    elapsed = (time.perf_counter() - start) / 100

    assert elapsed < 0.01  # < 10ms


def test_first_compute_speed():
    """单只股票首次计算应 < 1 秒"""
    updater = IncrementalUpdater(config=test_config)

    start = time.perf_counter()
    updater.update_symbol("000002")
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0  # < 1s


def test_incremental_update_speed():
    """增量更新应 < 100ms（仅更新 1-2 行）"""
    updater = IncrementalUpdater(config=test_config)
    updater.update_symbol("000001")  # 首次

    start = time.perf_counter()
    updater.update_symbol("000001")  # 增量
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1  # < 100ms
```

### 11.11.3 集成测试

```python
# tests/integration/test_precompute_e2e.py


def test_end_to_end_precompute_pipeline():
    """端到端预计算流程"""
    # 1. 全量下载
    from data.downloader import DownloadManager
    dm = DownloadManager("akshare")
    dm.downloader.download_stock("000001", "2024-01-01", "2024-12-31")

    # 2. 增量预计算
    updater = IncrementalUpdater(config=test_config)
    result = updater.update_symbol("000001")
    assert result["new_rows"] > 0

    # 3. 加载预计算结果
    df = updater.load_processed("000001")
    assert "MA60" in df.columns  # 指标已计算
    assert "ATR" in df.columns
    assert "KD" in df.columns  # 注意 K/D 不能作为单列名（用了 KD）

    # 4. 验证预计算 vs 实时计算结果一致
    from indicators.pipeline import calc_indicators_with_cache
    df2 = calc_indicators_with_cache("000001")
    pd.testing.assert_frame_equal(df, df2)
```

---

> 📌 **本开发文档完成**。涵盖：架构、数据、指标、状态、选股、信号、风控、回测、配置、部署、开发、**预计算系统**。