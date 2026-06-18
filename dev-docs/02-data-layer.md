# 02 - 数据层（基于金玥数据）

## 2.1 职责

负责所有数据相关的工作。基于**金玥数据**（本地 CSV）：

1. **数据加载**：读取金玥数据 CSV（data-by-day / data-by-stock）
2. **字段标准化**：中文全角列名 → 英文标准列名
3. **数据清洗**：退市时间'-'→NaT、是/否→bool、代码补后缀
4. **指标计算**：MACD/KDJ/RSI/BOLL/ATR/OBV 等（数据中无）
5. **数据缓存**：计算结果缓存到 Parquet
6. **数据校验**：完整性、一致性

## 2.2 模块结构

```
data/
├── __init__.py
├── loader.py            # 数据加载（核心）
├── column_mapper.py     # 列名映射（中文→英文）
├── cleaner.py           # 数据清洗（'-' / 是/否 / 名称）
├── storage.py           # Parquet 缓存
├── validator.py         # 数据校验
├── universe.py          # 股票池（HS300/CSI1000 等）
└── indicators.py        # 技术指标计算（单独文档）
```

## 2.3 数据源：金玥数据

| 维度 | 详情 |
|---|---|
| 来源 | 金玥数据（本地 CSV） |
| 时间范围 | data-by-day: 2018-2026（8.4 年）<br>data-by-stock: 2000-2026（最长 26 年） |
| 字段数 | 38 列 |
| 股票数 | 5841 只（含北交所） |
| 复权方式 | 不复权（按 README 说明） |
| 涨跌幅限制 | 主板 ±10%、创/科 ±20%、ST ±5%、北交所 ±30% |

> **重要**：ATOS 策略要求 2016-2025 完整 10 年。当前 data-by-day 缺 2016-2017，需用 data-by-stock 兜底。

## 2.4 两种数据组织方式

### 2.4.1 data-by-day/（横截面）

```
data/data-by-day/
├── 2018/
│   ├── 2018-01-02_金玥数据.csv
│   └── ...
├── 2019/
└── ... (2018-2026 共 9 个年份目录)
```

- **路径**：`data/data-by-day/{YYYY}/{YYYY-MM-DD}_金玥数据.csv`
- **每年文件数**：~243
- **总文件数**：~2267
- **单文件大小**：~1.5-1.6 MB
- **每文件记录数**：4000-5000 行（全 A 当日所有股票）
- **适合**：截面因子计算、选股、当日诊断、Phase 2 组合回测

### 2.4.2 data-by-stock/（时间序列）

```
data/data-by-stock/
├── 000001_金玥数据.csv
├── 000002_金玥数据.csv
└── ... (5841 只股票)
```

### 2.4.3 data-benchmark/（大盘指数，**关键**）

**v8.1 新增**：补 10 个大盘指数数据（用 baostock 下载）。

```
data/data-benchmark/
├── 2016/
│   ├── hs300_2016_benchmark.csv          # 沪深 300（主大盘基准）
│   ├── sse_index_2016_benchmark.csv     # 上证指数
│   ├── sse50_2016_benchmark.csv          # 上证 50
│   ├── csi500_2016_benchmark.csv         # 中证 500
│   ├── csi1000_2016_benchmark.csv        # 中证 1000
│   ├── csi_consumer_2016_benchmark.csv   # 中证消费
│   ├── csi_pharma_2016_benchmark.csv     # 中证医药
│   ├── csi_finance_2016_benchmark.csv    # 中证金融
│   ├── chinext_2016_benchmark.csv        # 创业板指
│   └── szse_component_2016_benchmark.csv # 深证成指
├── 2017/ ... 2025/
└── 10 年 × 10 指数 = 100 个文件 ≈ 3.7 MB
```

#### 10 个核心指数

| # | 名称 | baostock 代码 | 用途 |
|---|---|---|---|
| 1 | 沪深 300 | sh.000300 | **主大盘基准 + 4 状态识别** |
| 2 | 上证指数 | sh.000001 | 上证基准 |
| 3 | 上证 50 | sh.000016 | 超大盘 |
| 4 | 中证 500 | sh.000905 | 中盘 |
| 5 | 中证 1000 | sh.000852 | 小盘 |
| 6 | 中证消费 | sh.000932 | 消费板块 |
| 7 | 中证医药 | sh.000933 | 医药板块 |
| 8 | 中证金融 | sh.000934 | 金融板块 |
| 9 | 创业板指 | sz.399006 | 成长基准 |
| 10 | 深证成指 | sz.399001 | 深证基准 |

#### 字段规范（与金玥数据统一）

| 字段 | 类型 | 说明 |
|---|---|---|
| date | string | YYYY-MM-DD |
| open/high/low/close | float | OHLC |
| volume/amount | int | 成交量/额 |
| MA5/10/20/30/60/120/250 | float | 7 条均线（自动补全） |
| is_limit_up | bool | 指数无涨跌停，固定 False |

**重要**：baostock **不支持 ETF 数据**（510300、510500 等无数据），
所以用沪深 300 指数（sh.000300）作为"大盘基准 + 4 状态识别"输入。
策略文档 ATOS-des.md §1.1 提到的"沪深 300 ETF"在 dev-docs 中**改用指数**实现。

#### 数据获取脚本

```python
# scripts/download_benchmark.py
import baostock as bs
import pandas as pd
from pathlib import Path

INDICES = [
    ("沪深300",   "sh.000300", "hs300"),
    ("上证指数",  "sh.000001", "sse_index"),
    ("上证50",    "sh.000016", "sse50"),
    ("中证500",   "sh.000905", "csi500"),
    ("中证1000",  "sh.000852", "csi1000"),
    ("中证消费",  "sh.000932", "csi_consumer"),
    ("中证医药",  "sh.000933", "csi_pharma"),
    ("中证金融",  "sh.000934", "csi_finance"),
    ("创业板指",  "sz.399006", "chinext"),
    ("深证成指",  "sz.399001", "szse_component"),
]

OUTPUT_DIR = Path("data/data-benchmark")

def download_one(name, code, suffix):
    rs = bs.query_history_k_data_plus(
        code, "date,open,high,low,close,volume,amount",
        start_date="2016-01-01", end_date="2025-12-31",
        frequency="d", adjustflag="2"
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    df = pd.DataFrame(rows, columns=rs.fields)

    # 类型转换
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])

    # 清洗
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    df = df.sort_values("date").reset_index(drop=True)

    # 标准化字段
    result = pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "open": df["open"], "high": df["high"],
        "low": df["low"], "close": df["close"],
        "volume": df["volume"].fillna(0).astype("int64"),
        "amount": df["amount"].fillna(0).astype("int64"),
    })

    # 补全均线
    for n in [5, 10, 20, 30, 60, 120, 250]:
        result[f"MA{n}"] = result["close"].rolling(n, min_periods=1).mean().round(3)

    result["is_limit_up"] = False
    result["is_limit_down"] = False

    # 按年分目录保存
    result["date_dt"] = pd.to_datetime(result["date"])
    for year, year_df in result.groupby(result["date_dt"].dt.year):
        year_dir = OUTPUT_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        year_df.drop(columns=["date_dt"]).to_csv(
            year_dir / f"{suffix}_{year}_benchmark.csv", index=False
        )

    return len(result)


if __name__ == "__main__":
    bs.login()
    for name, code, suffix in INDICES:
        n = download_one(name, code, suffix)
        print(f"  {name} ({code}): {n} rows")
    bs.logout()
```

**实际下载结果**：
- 10/10 成功
- 10 年 × 2430 行 = 24,300 总行数
- 36.3 秒完成
- 总大小 3.7 MB

#### 加载接口

```python
def load_benchmark(
    name: str = "hs300",  # 简称，如 "hs300", "csi500"
    start: str = None,
    end: str = None
) -> pd.DataFrame:
    """加载大盘指数数据

    Args:
        name: 简称（hs300 / sse_index / sse50 / csi500 / csi1000 /
              csi_consumer / csi_pharma / csi_finance / chinext / szse_component）
        start: 起始日期
        end: 结束日期

    Returns:
        含全部字段的 DataFrame
    """
    dfs = []
    base_dir = Path("data/data-benchmark")
    for year_dir in sorted(base_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        file_path = year_dir / f"{name}_{year_dir.name}_benchmark.csv"
        if file_path.exists():
            year_df = pd.read_csv(file_path)
            dfs.append(year_df)

    if not dfs:
        raise FileNotFoundError(f"No data for benchmark: {name}")

    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]

    return df.reset_index(drop=True)
```

- **路径**：`data/data-by-stock/{XXXXXX}_金玥数据.csv`
- **单只股票**全部历史日线
- **每只股票**：上市日 ~ 2026-05-14
- **适合**：单股 K 线回放、长周期回测、单股深度分析

## 2.5 38 列 Schema

### 2.5.1 标识 / 元信息（4 列）

| 字段 | 类型 | 说明 |
|---|---|---|
| `日期` | string `YYYY-MM-DD` | 交易日 |
| `代码` | string 6 位 | 纯数字，无交易所后缀 |
| `名称` | string | 含全角空格（如 `万  科Ａ`） |
| `所属行业` | string | 行业分类 |

### 2.5.2 行情（6 列）

`开盘价` / `最高价` / `最低价` / `收盘价`（元）/ `前收盘价`（元）/ `振幅%`

### 2.5.3 成交（4 列）

`成交量（股）` / `成交额（元）` / `换手率`（%）/ `量比`（倍）

### 2.5.4 涨跌相关（6 列）

`涨幅%` / `3日涨幅%` / `6日涨幅%` / `10日涨幅%` / `25日涨幅%` / `是否涨停`（`是`/`否`）

### 2.5.5 股本 / 市值（4 列）

`总股本（股）` / `流通股本（股）` / `总市值（元）` / `流通市值（元）`

### 2.5.6 估值（3 列）

`滚动市盈率` / `市净率` / `滚动市销率`

### 2.5.7 均线（7 列）

`5日线` / `10日线` / `20日线` / `60日线` / `120日线` / `250日线`（元，简单移动平均）

修复 B1-05: 金玥数据**未提供 MA30**（文档误列）；如需 MA30 应在指标层计算

### 2.5.8 状态（4 列）

`是否ST`（`是`/`否`）/ `是否融资融券`（`是`/`否`/空）/ `上市时间`（`YYYY-MM-DD`）/ `退市时间`（未退市为 **`-`**，单字符减号）

## 2.6 核心接口

### 2.6.1 加载单日横截面

```python
from typing import Optional
import pandas as pd


def load_daily_cross_section(
    date: str,  # "2024-01-02"
    data_dir: str = "data/data-by-day"
) -> pd.DataFrame:
    """加载单日全市场横截面数据

    Args:
        date: 交易日（YYYY-MM-DD）
        data_dir: data-by-day 根目录

    Returns:
        DataFrame 含 38 列（已做列名映射和基础清洗）
    """
    from pathlib import Path
    year = date[:4]
    csv_path = Path(data_dir) / year / f"{date}_金玥数据.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Data not found: {csv_path}")

    df = pd.read_csv(csv_path, dtype={"代码": str, "名称": str})
    df = clean_dataframe(df)
    df = standardize_columns(df)

    return df
```

### 2.6.2 加载单只股票时间序列

```python
def load_stock_series(
    symbol: str,  # "000001"
    data_dir: str = "data/data-by-stock",
    start: Optional[str] = None,
    end: Optional[str] = None
) -> pd.DataFrame:
    """加载单只股票时间序列

    Args:
        symbol: 6 位股票代码
        data_dir: data-by-stock 根目录
        start: 起始日期（可选）
        end: 结束日期（可选）

    Returns:
        DataFrame 含 38 列（已做列名映射和基础清洗）
    """
    from pathlib import Path
    csv_path = Path(data_dir) / f"{symbol}_金玥数据.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Stock data not found: {csv_path}")

    df = pd.read_csv(csv_path, dtype={"代码": str, "名称": str})
    df = clean_dataframe(df)
    df = standardize_columns(df)

    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["date"] <= pd.Timestamp(end)]

    return df.reset_index(drop=True)
```

### 2.6.3 加载单只股票横截面（多个日期）

```python
def load_stock_cross_section(
    symbol: str,
    dates: list[str],
    data_dir: str = "data/data-by-day"
) -> pd.DataFrame:
    """加载单只股票在多个日期的横截面数据

    Args:
        symbol: 6 位股票代码
        dates: 日期列表
        data_dir: data-by-day 根目录

    Returns:
        DataFrame（只包含该股票的行）
    """
    dfs = []
    for date in dates:
        try:
            df_daily = load_daily_cross_section(date, data_dir)
            df_stock = df_daily[df_daily["代码"] == symbol]
            if not df_stock.empty:
                dfs.append(df_stock)
        except FileNotFoundError:
            continue

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)
```

## 2.7 列名映射（中文 → 英文）

```python
# data/column_mapper.py

COLUMN_MAPPING = {
    # 标识
    "日期": "date",
    "代码": "code",
    "名称": "name",
    "所属行业": "industry",

    # 行情
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "前收盘价": "prev_close",
    "振幅%": "amplitude",

    # 成交
    "成交量（股）": "volume",
    "成交额（元）": "amount",
    "换手率": "turnover",
    "量比": "vol_ratio",

    # 涨跌
    "涨幅%": "pct_change",
    "3日涨幅%": "pct_change_3d",
    "6日涨幅%": "pct_change_6d",
    "10日涨幅%": "pct_change_10d",
    "25日涨幅%": "pct_change_25d",
    "是否涨停": "is_limit_up",

    # 股本/市值
    "总股本（股）": "total_shares",
    "流通股本（股）": "float_shares",
    "总市值（元）": "mkt_cap_total",
    "流通市值（元）": "mkt_cap_float",

    # 估值
    "滚动市盈率": "pe_ttm",
    "市净率": "pb",
    "滚动市销率": "ps_ttm",

    # 均线
    "5日线": "MA5",
    "10日线": "MA10",
    "20日线": "MA20",
    "30日线": "MA30",
    "60日线": "MA60",
    "120日线": "MA120",
    "250日线": "MA250",

    # 状态
    "是否ST": "is_st",
    "是否融资融券": "is_margin",
    "上市时间": "list_date",
    "退市时间": "delist_date",
}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """列名标准化：中文 → 英文"""
    df = df.rename(columns=COLUMN_MAPPING)

    required = ["date", "code", "name", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return df
```

## 2.8 数据清洗（5 项必做）

```python
# data/cleaner.py
import pandas as pd
import numpy as np
import re


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """5 项必做清洗

    1. 代码补后缀
    2. 名称去全角空格
    3. 退市时间 '-' → NaT
    4. 日期 → pd.Timestamp
    5. 是/否 → bool
    """
    df = df.copy()

    # 1. 代码补后缀
    if "代码" in df.columns:
        df["代码"] = df["代码"].astype(str).apply(add_exchange_suffix)

    # 2. 名称去全角空格
    if "名称" in df.columns:
        df["名称"] = df["名称"].astype(str).apply(lambda x: re.sub(r"\s+", "", x))

    # 3. 退市时间 '-' → NaT
    if "退市时间" in df.columns:
        df["退市时间"] = pd.to_datetime(df["退市时间"], errors="coerce")

    # 4. 日期 → pd.Timestamp
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])

    # 5. 是/否 → bool
    bool_columns = ["是否ST", "是否涨停", "是否融资融券"]
    for col in bool_columns:
        if col in df.columns:
            df[col] = df[col].map(
                lambda x: True if str(x).strip() == "是" else False
            )

    return df


def add_exchange_suffix(code: str) -> str:
    """6 位数字代码补交易所后缀

    映射：
    - 60xxxx / 68xxxx → SH（上交所）
    - 00xxxx / 30xxxx / 20xxxx → SZ（深交所）
    - 92xxxx / 83xxxx → BJ（北交所）
    """
    code = str(code).zfill(6)
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    elif code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    elif code.startswith(("92", "83")):
        return f"{code}.BJ"
    return code
```

## 2.9 A 股硬约束过滤

```python
# data/filters.py
import pandas as pd


def apply_a_share_filters(df: pd.DataFrame) -> pd.DataFrame:
    """A 股硬约束过滤

    修复 B1-01: 先用原 6 位代码过滤（后缀化之前），再补后缀
    """
    df = df.copy()

    # 1. 过滤北交所（92/83 前缀，原始 6 位代码）
    if "代码" in df.columns:
        raw_code = df["代码"].astype(str).str.replace(r"\.(SZ|SH|BJ)$", "", regex=True)
        df = df[~raw_code.str.startswith(("92", "83"))]

    # 2. 过滤 ST
    if "是否ST" in df.columns:
        df = df[df["是否ST"] == False]

    # 3. 过滤退市股
    if "退市时间" in df.columns:
        df = df[df["退市时间"].isna()]

    return df.reset_index(drop=True)


def filter_new_stocks(df: pd.DataFrame, current_date: pd.Timestamp,
                       min_listing_days: int = 60) -> pd.DataFrame:
    """新股过滤（动态）"""
    if "上市时间" not in df.columns:
        return df

    df = df.copy()
    df["上市时间"] = pd.to_datetime(df["上市时间"], errors="coerce")
    days_since_listing = (current_date - df["上市时间"]).dt.days
    return df[days_since_listing >= min_listing_days]
```

## 2.10 缓存设计

```python
# data/storage.py
import pandas as pd
from pathlib import Path


class ParquetCache:
    """Parquet 缓存（计算结果）"""

    def __init__(self, base_dir: str = "data/processed"):
        self.base_dir = Path(base_dir)

    def save(self, symbol: str, df: pd.DataFrame, category: str = "stock"):
        path = self.base_dir / category / f"{symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, compression="snappy", index=False)

    def load(self, symbol: str, category: str = "stock") -> pd.DataFrame:
        path = self.base_dir / category / f"{symbol}.parquet"
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def exists(self, symbol: str, category: str = "stock") -> bool:
        return (self.base_dir / category / f"{symbol}.parquet").exists()
```

## 2.11 完整加载示例

```python
# scripts/load_data_demo.py
"""数据加载演示"""
import sys
sys.path.insert(0, ".")

from data.loader import load_daily_cross_section, load_stock_series
from indicators import calc_all_indicators

# 1. 加载某日横截面
print("=== 加载 2024-01-02 横截面 ===")
df_daily = load_daily_cross_section("2024-01-02")
print(f"行数: {len(df_daily)}, 列数: {len(df_daily.columns)}")
print(f"前 5 列: {df_daily.columns[:5].tolist()}")

# 2. 加载某只股票时间序列
print("\n=== 加载 000001 时间序列 ===")
df_stock = load_stock_series("000001", start="2020-01-01", end="2024-12-31")
print(f"行数: {len(df_stock)}")
print(df_stock[["date", "code", "name", "close", "volume"]].head())

# 3. 计算指标
print("\n=== 计算技术指标 ===")
df_with_ind = calc_all_indicators(df_stock)
new_cols = [c for c in df_with_ind.columns if c not in df_stock.columns]
print(f"指标列数: {len(new_cols)}")
```

## 2.12 数据校验

```python
# data/validator.py
import pandas as pd
import logging


class DataValidator:
    """数据校验器（针对金玥数据）"""

    def __init__(self):
        self.logger = logging.getLogger("atos")

    def validate(self, df: pd.DataFrame) -> bool:
        checks = [
            self._check_columns(df),
            self._check_no_missing_price(df),
            self._check_positive_price(df),
            self._check_high_low(df),
            self._check_volume(df),
            self._check_date_order(df),
        ]
        return all(checks)

    def _check_columns(self, df: pd.DataFrame) -> bool:
        required = ["date", "code", "open", "high", "low", "close", "volume"]
        ok = all(c in df.columns for c in required)
        if not ok:
            self.logger.error("Missing required columns")
        return ok

    def _check_no_missing_price(self, df: pd.DataFrame) -> bool:
        ok = df[["open", "high", "low", "close"]].notna().all().all()
        return ok

    def _check_positive_price(self, df: pd.DataFrame) -> bool:
        ok = (df[["open", "high", "low", "close"]] > 0).all().all()
        return ok

    def _check_high_low(self, df: pd.DataFrame) -> bool:
        cond1 = (df["high"] >= df[["open", "close"]].max(axis=1)).all()
        cond2 = (df["low"] <= df[["open", "close"]].min(axis=1)).all()
        return cond1 and cond2

    def _check_volume(self, df: pd.DataFrame) -> bool:
        return (df["volume"] >= 0).all()

    def _check_date_order(self, df: pd.DataFrame) -> bool:
        return df["date"].is_monotonic_increasing
```

## 2.13 复权说明

金玥数据为**不复权数据**：
- `前收盘价` 字段存在 = 不复权特征
- 早期均线（MA120/MA250）逐步填充

**策略影响**：
- 短期回测（< 1 年）不受影响
- 长期回测应**自行前复权** 或 接受历史价格跳变

**建议**：信号层用 close/MA 比例，避免绝对价格敏感。

## 2.14 缺失数据处理

| 情况 | 处理 |
|---|---|
| 上市未满 250 日，MA120/MA250 为空 | 保持 NaN，用 `min_periods=1` |

## 2.14.1 涨跌停与停牌处理（修复 D5 + C12）

```python
# data/price_limits.py
import pandas as pd


def get_limit_threshold(row: pd.Series) -> float:
    """获取单只股票的涨停阈值（修复 C12: 区分板块）

    主板 ±10%、创/科 ±20%、ST ±5%、北交所 ±30%
    """
    code = str(row.get("代码", ""))
    is_st = row.get("是否ST", "否") == "是"

    if is_st:
        return 0.05
    if code.startswith(("92", "83")):  # 北交所
        return 0.30
    if code.startswith(("30", "688")):  # 创业板 / 科创板
        return 0.20
    return 0.10  # 主板


def is_limit_up(row: pd.Series) -> bool:
    """判断是否涨停（修复 C12: 区分板块阈值）"""
    threshold = get_limit_threshold(row)
    # 修复 B1-02: 误差 0.3% 与注释一致
    return row["pct_change"] >= threshold * (1 - 0.003)


def is_limit_down(row: pd.Series) -> bool:
    """判断是否跌停"""
    threshold = get_limit_threshold(row)
    return row["pct_change"] <= -threshold * 0.97


def is_one_word_limit_up(row: pd.Series) -> bool:
    """判断是否一字涨停（开盘=收盘=最高=最低=涨停价）"""
    return (
        row["open"] == row["high"] == row["low"] == row["close"] and
        is_limit_up(row)
    )


def is_suspended(row: pd.Series) -> bool:
    """判断是否停牌（成交量=0 且价格不变）"""
    return row["volume"] == 0 and row["close"] == row["prev_close"]


def apply_trading_constraints(df: pd.DataFrame) -> pd.DataFrame:
    """应用 A 股交易约束

    1. 过滤一字板（不能买入）
    2. 过滤停牌日（不交易）
    3. 标记涨停（可能次日溢价开盘）
    """
    df = df.copy()
    df["is_one_word_limit_up"] = df.apply(is_one_word_limit_up, axis=1)
    df["is_suspended"] = df.apply(is_suspended, axis=1)
    df["is_limit_up"] = df.apply(is_limit_up, axis=1)
    return df
```
| 退市股 - | 自动转 NaT |
| 节假日 | 无数据，正常 |
| 停牌 | 收盘价 = 前收盘价，成交量 = 0 |

## 2.15 性能基准

| 操作 | 数据量 | 时间 |
|---|---|---|
| 加载单只股票（26 年） | ~5000 行 | < 0.1s |
| 加载单日横截面 | 4000-5000 行 | < 0.2s |
| 加载 1 年横截面 | 243 文件 | ~5s |
| 加载全市场时间序列 | 5841 只 | ~30s（首次） |
| 计算 1 只股票指标 | 5000 行 | ~0.5s |
| 缓存后读取 | 任意 | < 0.05s |

## 2.16 错误处理清单

| 错误 | 原因 | 处理 |
|---|---|---|
| `FileNotFoundError` | 文件不存在 | 跳过 |
| `KeyError` | 列名不匹配 | `standardize_columns` |
| `ValueError: NaT` | 退市时间 '-' | `errors="coerce"` |
| `UnicodeDecodeError` | 编码 | `encoding="utf-8"` |

## 2.17 测试

```python
# tests/test_data.py
import pytest
import pandas as pd
from data.cleaner import clean_dataframe, add_exchange_suffix
from data.column_mapper import standardize_columns


def test_add_exchange_suffix():
    """交易所后缀映射"""
    assert add_exchange_suffix("000001") == "000001.SZ"
    assert add_exchange_suffix("600000") == "600000.SH"
    assert add_exchange_suffix("688001") == "688001.SH"
    assert add_exchange_suffix("920982") == "920982.BJ"


def test_standardize_columns():
    """列名映射"""
    df = pd.DataFrame({"日期": [1], "代码": ["000001"], "开盘价": [1.0]})
    df_std = standardize_columns(df)
    assert "date" in df_std.columns
    assert "code" in df_std.columns
    assert "open" in df_std.columns


def test_clean_delist_date():
    """退市时间 '-' → NaT"""
    df = pd.DataFrame({"退市时间": ["-", "2024-01-01", ""]})
    df_clean = clean_dataframe(df)
    assert pd.isna(df_clean["退市时间"].iloc[0])
    assert df_clean["退市时间"].iloc[1] == pd.Timestamp("2024-01-01")


def test_clean_st_flag():
    """是/否 → bool"""
    df = pd.DataFrame({"是否ST": ["是", "否", "", None]})
    df_clean = clean_dataframe(df)
    assert df_clean["是否ST"].iloc[0] == True
    assert df_clean["是否ST"].iloc[1] == False


def test_load_daily_cross_section():
    """加载横截面"""
    from data.loader import load_daily_cross_section
    df = load_daily_cross_section("2024-01-02")
    assert not df.empty
    assert "date" in df.columns
    assert "日期" not in df.columns
```

## 2.18 ATOS 适配性

| ATOS 需求 | 数据字段 | 满足度 |
|---|---|---|
| OHLCV | open/high/low/close/volume | ✅ 100% |
| 均线 MA5-250 | MA5-MA250 | ✅ 100% |
| 涨跌停判断 | is_limit_up, pct_change | ✅ 100% |
| ST/退市/上市过滤 | is_st, delist_date, list_date | ✅ 100% |
| 流通市值 | mkt_cap_float | ✅ 100% |
| 行业 | industry | ✅ 100% |
| 换手率/量比 | turnover, vol_ratio | ✅ 100% |
| 时间范围 | 2018-2026 | ⚠️ 缺 2016-2017 |
| 技术指标（MACD/KDJ等） | 需自己算 | ⚠️ 需补 |

**评估**：85/100，基本满足。

## 2.19 注意事项

1. **不复权**：金玥数据是不复权，长期回测需谨慎
2. **早期均线为空**：上市未满 250 日的 MA120/MA250 为 NaN
3. **2016-2017 缺失**：用 `data-by-stock/` 单股兜底
4. **代码格式**：存储为 `000001.SZ` 等带后缀格式
5. **缓存策略**：计算结果缓存到 `data/processed/`（详见 12-precompute.md）

## 2.20 预计算接口（衔接 12-precompute.md）

```python
# data/precompute_interface.py

def load_processed_stock(symbol: str,
                          version: str = "v1",
                          start: str = None,
                          end: str = None,
                          config=None) -> pd.DataFrame:
    """加载预计算的单只股票数据（含所有指标 + 状态 + 因子）

    Args:
        symbol: 6 位股票代码
        version: 缓存版本号
        start, end: 日期范围（可选）

    Returns:
        预计算 DataFrame（含 OHLCV + 指标 + 状态 + 因子）
    """
    path = Path(f"data/processed/{version}/stock/{symbol}.parquet")
    if not path.exists():
        # 缓存未命中，触发计算
        from precompute.incremental import IncrementalUpdater
        IncrementalUpdater(config=None).update_symbol(symbol)
    df = pd.read_parquet(path)
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df
```

