# 09 - 配置管理

## 9.1 职责

**集中管理所有可调参数**，使策略可配置、可调优、可 A/B 测试。

## 9.2 5 层参数结构

```
L1 核心不可调参数（T+1、印花税、涨跌停）
L2 核心可调参数（10+ 个）
L3 市场状态特化参数
L4 风格特化参数
L5 因子特化参数
```

## 9.3 StrategyConfig 类

```python
# config/strategy_config.py
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class StrategyConfig:
    """策略配置 - 所有可调参数集中管理（修复 [v8.3] D7: L1 标注）

    参数层级标注：
    - **L1 核心不可调**：策略根基，调整会破坏策略一致性
    - **L2 核心可调**：可适度调整优化整体风格
    - **L3 状态特化**：不同市场状态的不同参数集
    - **L4 风格特化**：市值/板块风格（暂未启用）
    - **L5 因子特化**：单因子微调
    """

    # === L1 核心不可调（修改会破坏策略）===
    symbol: str = "510300"                # L1 标的代码（影响回测标的）
    initial_capital: float = 1_000_000     # L1 初始资金（影响手续费最小额）

    # === L2 核心可调参数（10+）===

    # 状态识别
    bull_threshold: float = 70.0           # 牛市评分阈值
    bear_threshold: float = 30.0           # 熊市评分阈值
    crash_threshold: float = 15.0          # 崩盘评分阈值
    # 修复 B6: 补 CRASH 触发条件配置
    crash_volatility_th: float = 0.35       # 20日波动率阈值
    crash_5d_drawdown: float = -0.08       # 5日跌幅阈值
    crash_20d_drawdown: float = -0.15      # 20日跌幅阈值
    min_duration: int = 3                  # 状态连续日数
    cooldown_days: int = 5                 # 状态冷却期

    # 仓位（修复 [v8.3] E43: CRASH=0.00 与策略文档 §3 严格一致）
    target_vol: float = 0.15               # 目标波动率
    max_position: float = 0.95             # 最大仓位
    base_position: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 0.85, "SIDEWAYS": 0.55,
        "BEAR": 0.15, "CRASH": 0.00,      # 修复 E43: 0% (强制空仓) 而非 0.05
        "CHOPPY_BEAR": 0.15
    })

    # 止损
    # 修复 A2: 补 CHOPPY_BEAR 键（与 base_position 对称）
    atr_base_k: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 3.0, "SIDEWAYS": 2.0,
        "BEAR": 1.5, "CRASH": 1.0,
        "CHOPPY_BEAR": 1.5
    })
    # 修复 B2: 硬止损 BULL 专用 -8%（与策略文档一致）
    hard_stop_pct: float = -0.08
    # 修复 B7: ATR 倍数 k 范围 [1.2, 4.0]（与策略文档一致）
    atr_k_min: float = 1.2
    atr_k_max: float = 4.0

    # 修复 A4: 分批止盈按状态区分（按策略文档 §3）
    partial_take_profit: Dict[str, list] = field(default_factory=lambda: {
        "BULL": [
            {"threshold": 0.08, "ratio": 0.33, "desc": "浮盈 8% 减 1/3"},
            {"threshold": 0.15, "ratio": 0.50, "desc": "浮盈 15% 减半"}
        ],
        "SIDEWAYS": [
            {"threshold": 0.05, "ratio": 0.50, "desc": "浮盈 5% 减半"}
        ],
        "BEAR": [
            {"threshold": 0.03, "ratio": 1.00, "desc": "浮盈 3% 全走"}
        ],
        "CHOPPY_BEAR": [
            {"threshold": 0.03, "ratio": 0.33, "desc": "浮盈 3% 减 1/3"},
            {"threshold": 0.05, "ratio": 1.00, "desc": "浮盈 5% 全走"}
        ],
        "CRASH": []
    })

    # 持仓周期
    # 修复 A1: 持仓周期与策略文档 ATOS-des.md §3 严格一致
    base_holding_period: int = 20
    max_holding_days: Dict[str, int] = field(default_factory=lambda: {
        "BULL": 20,         # §3: BULL=20
        "SIDEWAYS": 10,     # §3: SIDEWAYS=10（修复前错为 20）
        "BEAR": 5,          # §3: BEAR=5（修复前错为 10）
        "CRASH": 1,         # 防御性配置
        "CHOPPY_BEAR": 5    # §5.2: ≤ 5 个交易日（与 BEAR 一致，因 CHOPPY_BEAR 是 BEAR 叠加）
    })

    # 选股（修复 [v8.5] H2: 按状态独立持仓只数）
    top_n_stocks: Dict[str, int] = field(default_factory=lambda: {
        "BULL": 8,
        "SIDEWAYS": 6,
        "BEAR": 4,
        "CRASH": 0,
        "CHOPPY_BEAR": 4,
    })
    factor_lookback: int = 120             # IC 滚动窗口

    # 开仓信号阈值（修复 [v8.5] D8: 与 §3 表一致）
    open_threshold_by_regime: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 0.70,
        "SIDEWAYS": 0.60,
        "BEAR": 0.75,
        "CHOPPY_BEAR": 0.75,
    })

    # 震荡下行专项规则撤销延后天数（修复 [v8.5] D7）
    choppy_bear_grace_days: int = 3

    # 资金管理
    # 修复 A7: 资金管理限额统一为负数（与策略语义一致："亏损"）
    single_stock_loss_limit: float = -0.03  # 单只最大亏损 -3%
    daily_loss_limit: float = -0.02         # 当日亏损 -2%
    monthly_loss_limit: float = -0.05       # 月度亏损 -5%
    quarterly_loss_limit: float = -0.10     # 季度亏损 -10%
    yearly_loss_limit: float = -0.15        # 年度亏损 -15%

    # 修复 [v8.4] A29 + B31: 自适应参数（ATOS-des.md §6.1）
    # 仓位宽度系数：沪深 300 成份股中站上 MA60 的比例，范围 [0.5, 1.0]
    market_breadth: float = 1.0  # 由 precompute 每日更新
    # 目标波动率（vol 自适应 k 公式）
    target_vol: float = 0.15
    # 滚动胜率（用于开仓阈值自适应）
    rolling_winrate_20d: float = 0.5
    # 实际波动率（用于 vol_adj）
    realized_vol_20d: float = 0.15

    # === 修复 [v8.5] H2: 单只上限动态收敛 ===
    # 修复 BULL 状态 8 × 15% = 120% > 100% 的数学矛盾
    # 实际单只上限 = min(配置上限, 总仓位上限 / 持仓只数 × 0.9)
    single_cap_safety_factor: float = 0.9  # 90% 留 10% 安全边距

    # 修复 H2: 单只仓位上限字典（来自 §3 表格）
    single_cap_max: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 0.15,
        "SIDEWAYS": 0.10,
        "BEAR": 0.05,
        "CRASH": 0.00,
        "CHOPPY_BEAR": 0.03,  # §5.2: 3%
    })

    # 震荡下行专项
    choppy_bear_score_th: int = 3          # 4 维满足 3 维触发
    choppy_bear_max_pos: float = 0.20
    choppy_bear_holding_days: int = 5
    choppy_bear_profit_1: float = 0.03
    choppy_bear_profit_2: float = 0.05
    choppy_bear_rebound_th: float = 0.05
    choppy_bear_volume_th: float = 1.5

    # === L3 状态特化参数（按状态独立一套）===
    # 已在 base_position / atr_base_k / max_holding_days 中体现

    # === L4 风格特化参数 ===
    style_exposure: Dict[str, float] = field(default_factory=lambda: {
        "large_cap": 0.6,
        "mid_cap": 0.3,
        "small_cap": 0.1
    })

    # === L5 因子特化参数（动态权重表）===
    factor_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """导出为字典（修复 E31: dataclass 默认值无 _ 前缀，直接导出即可）"""
        result = {}
        for k, v in self.__dict__.items():
            if not k.startswith("_") and not callable(v):
                result[k] = v
        return result

    def update(self, **kwargs):
        """动态更新参数（修复 [v8.3] D12 + [v8.4] A37: 审计日志 + 嵌套键支持）

        每次 update 都会记录：
        - 时间戳
        - 旧值 → 新值
        - 调用栈（可选）

        支持嵌套键（点号路径）：
        - config.update(atr_base_k__BULL=2.5)（用 __ 代替 .）
        - 或 config.update(**{"atr_base_k.BULL": 2.5})
        """
        import datetime
        import logging

        logger = logging.getLogger("atos.config")
        audit = []

        for k, v in kwargs.items():
            # 修复 [v8.4] A37: 支持嵌套键（如 atr_base_k.BULL）
            if "." in k:
                top_key, sub_key = k.split(".", 1)
                if not hasattr(self, top_key):
                    raise AttributeError(f"Unknown config key: {k}")
                container = getattr(self, top_key)
                if isinstance(container, dict):
                    old_value = container.get(sub_key)
                    container[sub_key] = v
                    audit.append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "key": k,
                        "old_value": str(old_value)[:200],
                        "new_value": str(v)[:200],
                    })
                    logger.info(f"Config update: {k} = {old_value} → {v}")
                else:
                    raise AttributeError(f"Config key {top_key} is not a dict: {k}")
            elif hasattr(self, k):
                old_value = getattr(self, k)
                setattr(self, k, v)
                audit.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "key": k,
                    "old_value": str(old_value)[:200],
                    "new_value": str(v)[:200],
                })
                logger.info(f"Config update: {k} = {old_value} → {v}")
            else:
                raise AttributeError(f"Unknown config key: {k}")

        # 保存审计日志
        self._audit_log = getattr(self, "_audit_log", []) + audit

    def get_audit_log(self) -> list:
        """获取配置变更审计日志（修复 D12）"""
        return getattr(self, "_audit_log", [])

    def effective_single_cap(self, regime: str) -> float:
        """计算状态对应的实际单只仓位上限（修复 [v8.5] H2）

        修复 BULL 状态 8 × 15% = 120% > 100% 的数学矛盾：
        实际单只上限 = min(配置上限, 总仓位上限 / 持仓只数 × safety_factor)

        Args:
            regime: 状态（BULL/SIDEWAYS/BEAR/CRASH/CHOPPY_BEAR）

        Returns:
            单只仓位上限（小数，如 0.1125 = 11.25%）

        Example:
            >>> config.effective_single_cap("BULL")
            0.1125  # min(0.15, 1.0/8 * 0.9)
        """
        configured = self.single_cap_max.get(regime, 0.10)
        # 持仓只数：从 top_n_stocks 取（dict 或 int）
        if isinstance(self.top_n_stocks, dict):
            target_n = self.top_n_stocks.get(regime, 8)
        else:
            target_n = self.top_n_stocks if self.top_n_stocks > 0 else 8

        # 总仓位上限（来自 base_position）
        total_cap = self.base_position.get(regime, 0.5)

        # 动态收敛：min(配置上限, 总仓位 / 只数 × safety_factor)
        derived_cap = total_cap / max(target_n, 1) * self.single_cap_safety_factor

        return min(configured, derived_cap)

    @classmethod
    def from_yaml(cls, path: str, validate: bool = True) -> "StrategyConfig":
        """从 YAML 加载（修复 [v8.3] D9: 集成校验）

        Args:
            path: YAML 文件路径
            validate: 是否在校验后加载（默认 True）

        Raises:
            ValueError: 配置非法时
        """
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)

        config = cls(**data)

        if validate:
            from config.validator import validate_config
            errors = validate_config(config)
            if errors:
                raise ValueError(
                    f"Config validation failed ({len(errors)} errors):\n"
                    + "\n".join(f"  - {e}" for e in errors)
                )

        return config

    def to_yaml(self, path: str):
        """保存到 YAML"""
        import yaml
        with open(path, "w") as f:
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True)
```

## 9.4 YAML 配置文件

```yaml
# config/params.yaml

# === 基础 ===
symbol: "510300"
initial_capital: 1000000

# === 状态识别 ===
bull_threshold: 70
bear_threshold: 30
crash_threshold: 15
# 修复 B6: 补 CRASH 触发条件
crash_volatility_th: 0.35
crash_5d_drawdown: -0.08
crash_20d_drawdown: -0.15
min_duration: 3
cooldown_days: 5

# === 仓位 ===
# 修复 [v8.3] E43: CRASH 强制空仓（0%），与策略文档 §3 表格一致
target_vol: 0.15
max_position: 0.95
base_position:
  BULL: 0.85
  SIDEWAYS: 0.55
  BEAR: 0.15
  CRASH: 0.00          # 强制空仓
  CHOPPY_BEAR: 0.15

# === 修复 [v8.5] H2: 单只仓位上限 ===
# 实际单只上限 = min(配置上限, 总仓位 / 持仓只数 × safety_factor)
single_cap_max:
  BULL: 0.15
  SIDEWAYS: 0.10
  BEAR: 0.05
  CRASH: 0.00
  CHOPPY_BEAR: 0.03
single_cap_safety_factor: 0.9

# === 止损 ===
# 修复 A2: 补 CHOPPY_BEAR 键
atr_base_k:
  BULL: 3.0
  SIDEWAYS: 2.0
  BEAR: 1.5
  CRASH: 1.0
  CHOPPY_BEAR: 1.5
hard_stop_pct: -0.08
# 修复 B7: ATR 倍数 k 范围
atr_k_min: 1.2
atr_k_max: 4.0

# 修复 A4: 分批止盈按状态区分
partial_take_profit:
  BULL:
    - {threshold: 0.08, ratio: 0.33, desc: "浮盈 8% 减 1/3"}
    - {threshold: 0.15, ratio: 0.50, desc: "浮盈 15% 减半"}
  SIDEWAYS:
    - {threshold: 0.05, ratio: 0.50, desc: "浮盈 5% 减半"}
  BEAR:
    - {threshold: 0.03, ratio: 1.00, desc: "浮盈 3% 全走"}
  CHOPPY_BEAR:
    - {threshold: 0.03, ratio: 0.33, desc: "浮盈 3% 减 1/3"}
    - {threshold: 0.05, ratio: 1.00, desc: "浮盈 5% 全走"}
  CRASH: []

# === 持仓周期 ===
# 修复 A1: 与策略文档 ATOS-des.md §3 严格一致
base_holding_period: 20
max_holding_days:
  BULL: 20         # §3
  SIDEWAYS: 10     # §3
  BEAR: 5          # §3
  CRASH: 1         # 防御性
  CHOPPY_BEAR: 5   # §5.2

# === 选股 ===
# 修复 [v8.5] H2: 按状态独立持仓只数
top_n_stocks:
  BULL: 8
  SIDEWAYS: 6
  BEAR: 4
  CRASH: 0
  CHOPPY_BEAR: 4
factor_lookback: 120

# === 修复 [v8.5] D8: 开仓信号阈值（与 §3 表一致）===
open_threshold_by_regime:
  BULL: 0.70
  SIDEWAYS: 0.60
  BEAR: 0.75
  CHOPPY_BEAR: 0.75

# === 修复 [v8.5] D7: 震荡下行撤销延后天数 ===
choppy_bear_grace_days: 3

# === 资金管理 ===
# 修复 A7: 统一为负数（与校验器和语义一致）
single_stock_loss_limit: -0.03
daily_loss_limit: -0.02
monthly_loss_limit: -0.05
quarterly_loss_limit: -0.10
yearly_loss_limit: -0.15

# === 自适应参数（修复 [v8.4] A29 + B31: ATOS-des.md §6.1）===
market_breadth: 1.0      # 市场宽度（每日预计算更新）
target_vol: 0.15          # 目标波动率
rolling_winrate_20d: 0.5  # 滚动胜率
realized_vol_20d: 0.15    # 实际波动率

# === 震荡下行 ===
choppy_bear_score_th: 3
choppy_bear_max_pos: 0.20
choppy_bear_holding_days: 5
choppy_bear_profit_1: 0.03
choppy_bear_profit_2: 0.05
choppy_bear_rebound_th: 0.05
choppy_bear_volume_th: 1.5

# === 因子权重（按状态）===
factor_weights:
  BULL:
    trend_ma60: 0.15
    ret_20d: 0.20
    ret_60d: 0.15
    vol_ratio_5_20: 0.10
    sharpe_60d: 0.05
  SIDEWAYS:
    rsi_14_centered: 0.20
    near_high_60: 0.30
    turnover_stability: 0.15
    vol_ratio_5_20: 0.10
  BEAR:
    sharpe_60d: 0.15
    turnover_stability: 0.20
    rsi_14_centered: 0.20
  CHOPPY_BEAR:
    sharpe_60d: 0.20
    price_above_ma120: 0.20
    turnover_stability: 0.20
```

## 9.5 配置加载

```python
# config/__init__.py
from .strategy_config import StrategyConfig


def load_config(path: str = "config/params.yaml") -> StrategyConfig:
    """加载配置"""
    return StrategyConfig.from_yaml(path)


def save_config(config: StrategyConfig, path: str = "config/params.yaml"):
    """保存配置"""
    config.to_yaml(path)
```

## 9.6 配置使用示例

```python
# main.py
from config import load_config
from backtest.engine import BacktestEngine

# 加载配置
config = load_config("config/params.yaml")

# 修改单个参数（不修改文件）
config.bull_threshold = 75
config.atr_base_k["BULL"] = 2.5

# 回测
engine = BacktestEngine(config)
result = engine.run(df)
```

## 9.7 A/B 测试支持

```python
# config/ab_test.py
def create_variant(base_config: StrategyConfig,
                    param_name: str,
                    new_value) -> StrategyConfig:
    """创建配置变体（用于 A/B 测试）"""
    from copy import deepcopy
    variant = deepcopy(base_config)
    setattr(variant, param_name, new_value)
    return variant


# 使用
config_a = load_config()  # 基线
config_b = create_variant(config_a, "bull_threshold", 75)  # 变体

engine_a = BacktestEngine(config_a)
engine_b = BacktestEngine(config_b)

result_a = engine_a.run(df)
result_b = engine_b.run(df)

# 对比
print(f"A: 年化 {result_a.metrics['annual_return']:.2%}, 夏普 {result_a.metrics['sharpe']:.2f}")
print(f"B: 年化 {result_b.metrics['annual_return']:.2%}, 夏普 {result_b.metrics['sharpe']:.2f}")
```

## 9.8 配置版本管理

```
config/
├── params.yaml              # 当前配置
├── params_v1.yaml           # 历史版本
├── params_v2.yaml
└── params_test.yaml         # 测试配置
```

## 9.9 配置校验

```python
# config/validator.py
def validate_config(config: StrategyConfig) -> list[str]:
    """校验配置合法性（修复 [v8.4] A40: 移除废弃的评分阈值校验）

    Returns:
        错误列表（空 = 通过）

    修复说明：
    - ATOS-des.md §2.1 已改为布尔规则，bull/bear/crash 阈值已废弃
    - 保留字段仅为向后兼容
    """
    errors = []

    # [v8.4] A40: bull_threshold/bear_threshold/crash_threshold 已废弃，
    # 不再校验三者关系（布尔规则版直接用硬编码条件）
    # 字段保留仅用于 to_yaml 兼容性

    # 仓位范围（保留）
    for state, pos in config.base_position.items():
        if not 0 <= pos <= 1:
            errors.append(f"base_position[{state}] 必须在 [0, 1]")

    # ATR k 范围
    for state, k in config.atr_base_k.items():
        if not 0 < k <= 5:
            errors.append(f"atr_base_k[{state}] 必须在 (0, 5]")

    # 资金管理
    if config.daily_loss_limit > 0:
        errors.append("daily_loss_limit 应为负数或零")
    if config.yearly_loss_limit > 0:
        errors.append("yearly_loss_limit 应为负数或零")

    # [v8.4] A29: market_breadth 必须 [0.5, 1.0]
    if not 0.5 <= config.market_breadth <= 1.0:
        errors.append(f"market_breadth {config.market_breadth} 不在 [0.5, 1.0]")

    # [v8.5] H2: single_cap_max 各值在 [0, 1]
    if hasattr(config, "single_cap_max"):
        for state, cap in config.single_cap_max.items():
            if not 0 <= cap <= 1:
                errors.append(f"single_cap_max[{state}] {cap} 必须在 [0, 1]")

    # [v8.5] H2: top_n_stocks 必须包含所有状态
    if isinstance(config.top_n_stocks, dict):
        required_states = {"BULL", "SIDEWAYS", "BEAR", "CRASH", "CHOPPY_BEAR"}
        missing = required_states - set(config.top_n_stocks.keys())
        if missing:
            errors.append(f"top_n_stocks 缺少状态: {missing}")

    # [v8.5] D7: choppy_bear_grace_days >= 0
    if getattr(config, "choppy_bear_grace_days", 3) < 0:
        errors.append("choppy_bear_grace_days 必须 >= 0")

    # [v8.5] D8: open_threshold_by_regime 各值在 [0, 1]
    if hasattr(config, "open_threshold_by_regime"):
        for state, th in config.open_threshold_by_regime.items():
            if not 0 <= th <= 1:
                errors.append(f"open_threshold_by_regime[{state}] {th} 必须在 [0, 1]")

    return errors
```

## 9.10 文档化

每个配置项应自动生成文档：

```python
# config/doc_gen.py
def generate_config_doc(config: StrategyConfig, output_path: str):
    """生成配置文档"""
    with open(output_path, "w") as f:
        f.write("# 策略配置文档\n\n")
        for key, value in config.to_dict().items():
            f.write(f"- `{key}`: {value}\n")
```