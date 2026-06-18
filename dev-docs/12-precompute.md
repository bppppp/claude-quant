# 12 - 预计算系统（v7.0 性能优化版）

## 12.1 目标

将所有**可在 T+1 前**计算完成的指标、因子、状态**一次性预计算 + 缓存**，
使得运行时（T+1 决策）只做轻量工作。

| 阶段 | 耗时（不预计算） | 耗时（预计算后） | 提升 |
|---|---|---|---|
| 单只股票全指标 | 50ms | 5ms（缓存） | 10x |
| 全 A 股因子（5841 只） | 5 分钟 | 30 秒（首日）<br>5 秒（增量） | 10-60x |
| 完整回测（10 年） | 30 分钟 | 5 分钟 | 6x |
| Walk-Forward（5 轮） | 2.5 小时 | 30 分钟 | 5x |

## 12.2 预计算清单

### 12.2.1 数据层预计算

| 预计算项 | 频率 | 存储位置 | 大小估算 |
|---|---|---|---|
| 38 字段标准化结果 | 每日增量 | `data/processed/stock/{symbol}.parquet` | ~2 MB/只 |
| 涨跌停标记 | 每日 | 同上 | — |
| 停牌标记 | 每日 | 同上 | — |
| 北交所过滤 | 一次性 | 内存常量 | — |
| ST/退市过滤 | 每日 | 同上 | — |
| **大盘指数 10 标的**（**v8.1 新增**） | 一次性 + 每日增量 | `data/processed/market/{name}.parquet` | ~2 MB/标 |

**v8.1 新增大盘预计算**：
- 10 个指数 × 10 年 ≈ 24,300 行
- 用 baostock 下载
- 预计算后存为 Parquet（`data/processed/market/hs300.parquet` 等）

### 12.2.2 指标层预计算

13 个技术指标 × 5841 只股票 × 2500 日 ≈ **1.9 亿行**

| 预计算项 | 频率 | 备注 |
|---|---|---|
| MA5/10/20/30/60/120/250 | 每日增量 | 数据已有 7 条 |
| MACD (DIF/DEA/MACD柱) | 每日增量 | 需要 ewm |
| KDJ (K/D/J) | 每日增量 | — |
| RSI (6/12/24) | 每日增量 | — |
| BOLL (中/上/下/宽/%b) | 每日增量 | — |
| ATR (14) | 每日增量 | DMI 内部已算，避免重复 |
| DMI (PDI/NDI/ADX) | 每日增量 | — |
| Donchian (上/下/中) | 每日增量 | — |
| OBV/OBV_MA | 每日增量 | — |
| MFI (14) | 每日增量 | — |
| 量比 | 数据已有 | 跳过 |
| 均线粘合度 | 每日增量 | 自定义 |
| 均线排列强度 | 每日增量 | 自定义 |

**总大小估算**：5841 × 2500 × 30 字段 × 4 bytes ≈ **1.5 GB**（Parquet 压缩后 ~500 MB）

### 12.2.3 状态层预计算

| 预计算项 | 频率 | 存储位置 | 备注 |
|---|---|---|---|
| 大盘 4 状态（沪深 300） | 每日 | `data/processed/market/000300.parquet` | 单标的状态机 |
| 大盘趋势强度评分 | 每日 | 同上 | — |
| 震荡下行检测 | 每日 | 同上 | — |
| 大盘波动率 | 每日 | 同上 | — |

**大小估算**：1 只 × 2500 日 × 10 字段 = 极小

### 12.2.4 选股层预计算

| 预计算项 | 频率 | 存储位置 | 大小估算 |
|---|---|---|---|
| 个股 12 因子（原始） | 每日增量 | `data/processed/factors/{symbol}.parquet` | ~3 MB/只 |
| **每日全市场横截面日榜** | 每日 | `data/processed/selection/{YYYY-MM-DD}.parquet` | ~1 MB/日 |

**横截面日榜**包含：
- 当日所有可交易股票（~5000 只）
- 12 因子横截面标准化值
- 综合得分（按市场状态权重）
- 行业、市值分位

**年总大小**：250 × 1 MB = 250 MB

### 12.2.5 辅助预计算

| 预计算项 | 频率 | 存储位置 | 备注 |
|---|---|---|---|
| 交易日历 | 一次性 | `data/processed/meta/trading_days.parquet` | A 股交易日列表 |
| 股票池列表 | 半年更新 | `data/processed/meta/universe.parquet` | HS300/CSI1000 成分股 |
| 行业分类 | 半年更新 | `data/processed/meta/industry.parquet` | 申万一级 |
| 涨跌停阈值 | 一次性 | `data/processed/meta/price_limits.parquet` | 各板块涨跌幅 |

## 12.3 存储设计

### 12.3.1 目录结构

```
data/
├── raw/                            # 原始数据（已存在）
│   ├── data-by-day/
│   └── data-by-stock/
├── processed/                      # 预计算数据（新增）
│   ├── v1/                        # 版本号（数据 schema 升级时递增）
│   │   ├── stock/
│   │   │   ├── 000001.parquet     # 每只股票一个文件
│   │   │   ├── 000002.parquet
│   │   │   └── ...
│   │   ├── market/
│   │   │   └── 000300.parquet     # 大盘指数
│   │   ├── factors/
│   │   │   ├── 000001.parquet
│   │   │   └── ...
│   │   ├── selection/
│   │   │   ├── 2024-01-02.parquet # 每日横截面日榜
│   │   │   └── ...
│   │   └── meta/
│   │       ├── trading_days.parquet
│   │       ├── universe.parquet
│   │       ├── industry.parquet
│   │       └── price_limits.parquet
│   └── _meta/
│       ├── compute_log.json         # 预计算日志
│       └── version.json            # 当前版本
└── config/
    └── precompute.yaml             # 预计算配置
```

### 12.3.2 文件命名规范

| 文件 | 命名 | 示例 |
|---|---|---|
| 个股全数据 | `{symbol}.parquet` | `000001.parquet` |
| 大盘指数 | `{symbol}.parquet` | `000300.parquet` |
| 每日横截面 | `{YYYY-MM-DD}.parquet` | `2024-01-02.parquet` |
| Metadata | `{name}.parquet` | `trading_days.parquet` |

### 12.3.3 Parquet 优化

```python
# data/storage.py
import pyarrow as pa
import pyarrow.parquet as pq

# 优化选项
PARQUET_OPTIONS = {
    "compression": "snappy",      # 快速压缩
    "use_dictionary": True,        # 重复值用字典
    "dictionary_pagesize_limit": 1024 * 1024,
    "write_statistics": True,      # 列统计
    "row_group_size": 50000,       # 行组
    "data_page_size": 1024 * 1024  # 页大小
}


def save_optimized(df: pd.DataFrame, path: Path):
    """优化的 Parquet 保存"""
    # 1. 优化 dtype：float64 → float32 节省 50% 空间
    for col in df.select_dtypes(include=['float64']).columns:
        df[col] = df[col].astype('float32')

    # 2. 优化 dtype：int64 → int32（值域够用时）
    for col in df.select_dtypes(include=['int64']).columns:
        if df[col].max() < 2**31:
            df[col] = df[col].astype('int32')

    # 3. category 优化（重复值多时）
    for col in df.select_dtypes(include=['object']).columns:
        if df[col].nunique() / len(df) < 0.5:
            df[col] = df[col].astype('category')

    # 4. 保存
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path, **PARQUET_OPTIONS)
```

### 12.3.4 索引与分区

```python
# 个股 parquet 结构
# df 索引 = date（pd.DatetimeIndex）
# 列：
# - date（索引）
# - open, high, low, close, volume, amount（原数据）
# - MA5, MA10, MA20, ...（指标）
# - DIF, DEA, MACD（MACD）
# - K, D, J（KDJ）
# - RSI6, RSI12, RSI24
# - BOLL_MID, BOLL_UP, BOLL_DOWN, BOLL_WIDTH, BOLL_PB
# - ATR
# - PDI, NDI, ADX
# - DC_UP, DC_LOW, DC_MID
# - OBV, OBV_MA
# - MFI
# - VOL_RATIO
# - MA_ALIGN, MA_CONV（自定义）
```

### 12.3.5 Metadata Schema

```json
// data/processed/_meta/version.json
{
    "version": 1,
    "created_at": "2024-01-15T10:00:00",
    "schema": {
        "stock": {
            "columns": ["date", "open", "high", "low", "close"],
            "dtypes": {"date": "datetime64[ns]", "close": "float32"},
            "row_count": 2500,
            "date_range": ["2016-01-04", "2025-12-31"]
        },
        "selection": {
            "columns": ["symbol", "name", "industry", "composite_score"],
            "row_count": 5000
        }
    },
    "compute_params": {
        "ma_periods": [5, 10, 20, 30, 60, 120, 250],
        "macd_params": [12, 26, 9],
        "kdj_params": [9, 3, 3]
    }
}
```

## 12.4 增量更新策略

```python
# precompute/incremental.py
import pandas as pd
from pathlib import Path
from datetime import timedelta


class IncrementalUpdater:
    """增量更新器"""

    def __init__(self, config):
        self.config = config
        self.cache_dir = Path("data/processed/v1")

    def update_symbol(self, symbol: str) -> dict:
        """增量更新单只股票的所有预计算项

        Returns:
            {
                "incremental": True/False,
                "new_rows": int,
                "compute_time": float
            }
        """
        import time
        start = time.time()

        cache_path = self.cache_dir / "stock" / f"{symbol}.parquet"
        raw_path = Path(f"data/data-by-stock/{symbol}_金玥数据.csv")

        # 1. 加载原始数据
        from data.loader import load_stock_series
        raw = load_stock_series(symbol, data_dir="data/data-by-stock")

        # 2. 检查是否需要增量
        if cache_path.exists():
            cached = pd.read_parquet(cache_path)
            last_date = cached.index.max()
            new_data = raw[raw["date"] > last_date]
            if new_data.empty:
                return {"incremental": False, "new_rows": 0}
        else:
            cached = None
            new_data = raw

        # 3. 加载预计算的指标计算函数
        from indicators.pipeline import calc_indicators_with_cache
        new_indicators = calc_indicators_with_cache(
            symbol, df=new_data, force_recalc=True
        )

        # 4. 拼接
        if cached is not None:
            combined = pd.concat([cached, new_indicators]).sort_index()
            combined = combined[~combined.index.duplicated(keep="last")]
        else:
            combined = new_indicators

        # 5. 保存
        from data.storage import save_optimized
        save_optimized(combined, cache_path)

        return {
            "incremental": True,
            "new_rows": len(new_data),
            "compute_time": time.time() - start
        }
```

## 12.5 并行预计算

```python
# precompute/parallel.py
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import psutil


class ParallelPrecomputer:
    """并行预计算器（修复 [v8.4] A52/A56/A57/A58/A59/A60/A67）"""

    def __init__(self, config, cache_dir: str = "data/processed/v1"):
        self.config = config
        # 修复 [v8.4] A56: 显式接收 cache_dir 参数
        self.cache_dir = Path(cache_dir)
        # 智能确定 worker 数
        n_cpu = cpu_count()
        mem_gb = psutil.virtual_memory().total / (1024**3)
        # 每 worker 约 1 GB 内存
        max_by_mem = max(1, int(mem_gb / 1))
        # 取最小值
        n_workers_cfg = getattr(config, "n_workers", n_cpu - 1) if config else n_cpu - 1
        self.n_workers = min(n_workers_cfg, n_cpu - 1, max_by_mem)

    def precompute_all(self, force=False):
        """预计算所有标的"""
        # 1. 获取股票列表
        from data.universe import get_universe
        symbols = get_universe("HS300+CSI1000")

        # 2. 检查已有缓存，跳过已完成
        if not force:
            symbols = self.filter_pending(symbols)

        print(f"Processing {len(symbols)} symbols with {self.n_workers} workers")

        # 3. 并行执行
        results = []
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            futures = {
                executor.submit(
                    self._precompute_symbol_task, sym, force
                ): sym for sym in symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    result = future.result(timeout=300)
                    results.append(result)
                except Exception as e:
                    print(f"Failed: {sym}: {e}")

        return results

    @staticmethod
    def _precompute_symbol_task(symbol: str, force: bool):
        """worker 任务（静态方法以支持 pickle，修复 [v8.4] A67）"""
        from precompute.incremental import IncrementalUpdater
        updater = IncrementalUpdater(config=None)
        return updater.update_symbol(symbol)

    def precompute_daily_selection(self, date: str):
        """预计算某日全市场选股日榜

        修复 [v8.4] A57/A58/A59/A60:
        - A57: load_daily_cross_section 已自动调用 standardize_columns
        - A58: 用 daily[daily["code"] == symbol] 而非 daily.loc[symbol]
        - A59: _composite_score 签名修正（无 date 参数）
        - A60: 实现缺失的 get_regime_at_date 方法
        """
        from data.loader import load_daily_cross_section
        from selection.selector import StockSelector

        # 1. 加载当日全市场数据（已含英文列名）
        daily = load_daily_cross_section(date)

        # 2. 加载所有股票的预计算因子
        factor_dict = {}
        for symbol in daily["code"]:
            cache_path = self.cache_dir / "factors" / f"{symbol}.parquet"
            if cache_path.exists():
                factors = pd.read_parquet(cache_path)
                if date in factors.index:
                    factor_dict[symbol] = factors.loc[date]

        # 3. 横截面标准化 + 综合得分（修复 A60: get_regime_at_date 已实现）
        selector = StockSelector(self.config)
        regime = self.get_regime_at_date(date)

        # 4. 生成日榜（修复 A58: 用 boolean indexing 而非 .loc[symbol]）
        results = []
        for symbol in daily["code"]:
            if symbol in factor_dict:
                score = selector._composite_score(
                    factor_dict[symbol],
                    selector.factor_weights,
                    # 修复 A59: 不传 date 参数
                )
                # 修复 A58: 用 boolean indexing 获取 name
                name = daily.loc[daily["code"] == symbol, "name"].iloc[0] \
                    if not daily[daily["code"] == symbol].empty else symbol
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "composite_score": score,
                    "regime": regime
                })

        # 5. 保存
        day_df = pd.DataFrame(results)
        day_df.to_parquet(
            self.cache_dir / "selection" / f"{date}.parquet"
        )

    def get_regime_at_date(self, date: str) -> str:
        """获取某日的预计算市场状态（修复 [v8.4] A60 实现）

        Args:
            date: 日期字符串 YYYY-MM-DD

        Returns:
            str: 市场状态（"BULL" / "SIDEWAYS" / "BEAR" / "CRASH" / "CHOPPY_BEAR"）
        """
        regime_path = self.cache_dir / "regime" / f"{date}.parquet"
        if regime_path.exists():
            df = pd.read_parquet(regime_path)
            return df.loc[0, "effective_state"] if not df.empty else "SIDEWAYS"
        return "SIDEWAYS"  # 缺数据默认 SIDEWAYS
```

## 12.6 内存缓存层

```python
# precompute/cache.py
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable, Optional


class LRUCache:
    """LRU 内存缓存（线程安全）"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache = OrderedDict()
        self.lock = Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, loader: Optional[Callable] = None) -> Any:
        with self.lock:
            if key in self.cache:
                self.hits += 1
                self.cache.move_to_end(key)
                return self.cache[key]

            self.misses += 1
            if loader is not None:
                value = loader()
                self._put(key, value)
                return value
            return None

    def put(self, key: str, value: Any):
        with self.lock:
            self._put(key, value)

    def _put(self, key, value):
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[key] = value

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0,
            "size": len(self.cache),
            "max_size": self.max_size
        }
```

## 12.7 调度系统

```python
# precompute/scheduler.py
from datetime import datetime
import schedule
import time


class PrecomputeScheduler:
    """预计算调度器"""

    def __init__(self, config):
        self.config = config
        self.updater = IncrementalUpdater(config)
        self.parallel = ParallelPrecomputer(config)

    def start(self):
        """启动调度循环"""
        # 交易日 17:00 更新原始数据
        schedule.every().monday.at("17:00").do(self.daily_update_data)
        schedule.every().tuesday.at("17:00").do(self.daily_update_data)
        schedule.every().wednesday.at("17:00").do(self.daily_update_data)
        schedule.every().thursday.at("17:00").do(self.daily_update_data)
        schedule.every().friday.at("17:00").do(self.daily_update_data)

        # 17:30 预计算当日所有指标
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            getattr(schedule.every(), day).at("17:30").do(self.daily_precompute)

        # 18:00 生成次日选股日榜
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            getattr(schedule.every(), day).at("18:00").do(self.next_day_selection)

        # 每周日 22:00 全量校验
        schedule.every().sunday.at("22:00").do(self.weekly_full_check)

        while True:
            schedule.run_pending()
            time.sleep(60)

    def daily_update_data(self):
        """更新原始数据"""
        from data.updater import DataUpdater
        from data.downloader import DownloadManager
        from data.storage import ParquetStorage

        dm = DownloadManager("akshare")
        storage = ParquetStorage()
        updater = DataUpdater(storage, dm)
        updater.update_all(self.config.symbols)

    def daily_precompute(self):
        """预计算当日所有指标"""
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"[{today}] Starting precompute...")

        # 增量更新所有股票
        results = self.parallel.precompute_all(force=False)

        # 计算大盘状态
        self.update_market_regime()

        # 计算所有股票的状态（基于已缓存的指标）
        self.update_all_stock_regimes()

        print(f"[{today}] Precompute done: {len(results)} symbols updated")

    def next_day_selection(self):
        """生成次日选股日榜"""
        next_day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.parallel.precompute_daily_selection(next_day)
```

## 12.8 性能基准

| 操作 | 不预计算 | 预计算 | 提升 |
|---|---|---|---|
| 单只股票全指标 | 50ms | 5ms（缓存） | 10x |
| 全 A 股因子（5841 只） | 5 分钟 | 30 秒（首日）<br>5 秒（增量） | 10-60x |
| 大盘状态识别 | 100ms | 1ms（缓存） | 100x |
| 每日横截面选股 | 1 秒 | 100ms | 10x |
| 完整回测（10 年） | 30 分钟 | 5 分钟 | 6x |
| Walk-Forward（5 轮） | 2.5 小时 | 30 分钟 | 5x |
| 实盘 T+1 决策 | 5 分钟（全算） | 30 秒 | 10x |

## 12.9 完整预计算主流程

```
每日盘后 17:00 启动
   ↓
1. data.updater.update_all()
   - 增量下载新数据
   - 保存到 data/raw/
   ↓
2. parallel.precompute_all()
   - 4 worker 并行
   - 每只股票：load → calc_indicators → calc_factors → save
   - 跳过无变化的股票（hash 校验）
   - 预期：5841 只 × 5s = 30 分钟
   ↓
3. update_market_regime()
   - 加载大盘原始
   - 计算指标
   - detect_market_regime
   - 保存到 data/processed/market/000300.parquet
   - 预期：10s
   ↓
4. update_all_stock_regimes()
   - 每只股票：基于已缓存指标 + 大盘状态
   - 计算个股趋势强度、相对强弱等
   - 预期：1 分钟
   ↓
5. next_day_selection()
   - 加载次日全市场数据（已是 T+1 日，需要等到次日开盘）
   - 实际：每日生成"未来 1 周"的预选股清单
   - 预期：1 分钟
   ↓
全部完成
```

## 12.10 失败与回滚

```python
class PrecomputeResilience:
    """预计算弹性机制"""

    def validate_cache(self, symbol: str) -> bool:
        """校验缓存有效性"""
        cache_path = self.cache_dir / f"stock/{symbol}.parquet"
        if not cache_path.exists():
            return False

        # 1. 检查文件可读
        try:
            df = pd.read_parquet(cache_path)
        except:
            return False

        # 2. 检查必要列
        required = ["open", "high", "low", "close", "volume", "MA60", "ATR"]
        if not all(c in df.columns for c in required):
            return False

        # 3. 检查数据日期
        latest_date = df.index.max()
        raw_latest = self.get_raw_latest_date(symbol)
        if latest_date < raw_latest - timedelta(days=7):
            return False  # 缓存过期

        return True

    def recover_cache(self, symbol: str):
        """缓存恢复"""
        # 1. 备份损坏文件
        cache_path = self.cache_dir / f"stock/{symbol}.parquet"
        if cache_path.exists():
            backup_path = cache_path.with_suffix('.parquet.bak')
            cache_path.rename(backup_path)

        # 2. 全量重算
        self.full_recompute(symbol)

    def atomic_write(self, df, path):
        """原子写入：先写临时文件，再 rename"""
        tmp_path = path.with_suffix('.parquet.tmp')
        df.to_parquet(tmp_path)
        tmp_path.rename(path)  # 原子操作
```

## 12.11 监控

```python
class PrecomputeMonitor:
    """预计算监控"""

    def collect_metrics(self) -> dict:
        """采集指标"""
        cache_size_gb = sum(
            f.stat().st_size for f in self.cache_dir.rglob("*.parquet")
        ) / (1024**3)

        return {
            "cache_size_gb": cache_size_gb,
            "n_cached_stocks": len(list((self.cache_dir / "stock").glob("*.parquet"))),
            "n_selection_days": len(list((self.cache_dir / "selection").glob("*.parquet"))),
            "cache_hit_rate": self.cache.stats()["hit_rate"],
            "last_update": self.get_last_update_time()
        }
```

## 12.12 测试

```python
# tests/test_precompute.py

def test_incremental_update_creates_cache():
    """增量更新应创建缓存"""
    updater = IncrementalUpdater(config=test_config)
    result = updater.update_symbol("000001")
    assert result["new_rows"] > 0
    assert Path("data/processed/v1/stock/000001.parquet").exists()


def test_incremental_update_idempotent():
    """重复增量更新应幂等（修复 B11-05: 真实路径，不是字面字符串）"""
    updater = IncrementalUpdater(config=test_config)
    updater.update_symbol("000001")
    cache_path = updater.cache_dir / "stock" / "000001.parquet"
    first_size = cache_path.stat().st_size

    updater.update_symbol("000001")
    second_size = cache_path.stat().st_size

    # 大小不应增长（无新数据）
    assert first_size == second_size


def test_atomic_write():
    """原子写入：失败不应产生半成品"""
    # 模拟写入失败
    with mock.patch("pandas.DataFrame.to_parquet", side_effect=IOError):
        with pytest.raises(IOError):
            atomic_write(test_df, Path("/tmp/test.parquet"))
    assert not Path("/tmp/test.parquet.tmp").exists()
```

