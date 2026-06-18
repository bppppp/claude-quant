"""策略配置模块 - 所有可调参数集中管理"""
from dataclasses import dataclass, field
from typing import Dict
import datetime
import logging


@dataclass
class StrategyConfig:
    """策略配置 - 所有可调参数集中管理"""

    # === L1 核心不可调（修改会破坏策略）===
    symbol: str = "510300"
    initial_capital: float = 1_000_000
    commission_rate: float = 0.00025
    stamp_tax_rate: float = 0.001

    # === L2 核心可调参数 ===
    bull_threshold: float = 70.0
    bear_threshold: float = 30.0
    crash_threshold: float = 15.0
    crash_volatility_th: float = 0.35
    crash_5d_drawdown: float = -0.08
    crash_20d_drawdown: float = -0.15
    min_duration: int = 3
    cooldown_days: int = 5

    target_vol: float = 0.15
    max_position: float = 0.95
    base_position: Dict[str, float] = field(default_factory=lambda: {
        # ATOS11 v1: 更激进的仓位（target 25%+ annual）
        "BULL": 0.95, "SIDEWAYS": 0.70,
        "BEAR": 0.30, "CRASH": 0.00,
        "CHOPPY_BEAR": 0.30,
        # ATOS7 v1: 5 状态独立 Playbook
        "STAGE_1": 0.30,
        "STAGE_2": 0.70,
        "STAGE_3": 0.30,
        "STAGE_4": 0.10,
    })

    atr_base_k: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 3.0, "SIDEWAYS": 2.0,
        "BEAR": 1.5, "CRASH": 1.0,
        "CHOPPY_BEAR": 1.5
    })
    hard_stop_pct: float = -0.08
    atr_k_min: float = 1.2
    atr_k_max: float = 4.0

    partial_take_profit: Dict[str, list] = field(default_factory=lambda: {
        # ATOS11 v1: 降低止盈阈值（更频繁止盈）
        "BULL": [
            {"threshold": 0.05, "ratio": 0.33, "desc": "浮盈 5% 减 1/3"},
            {"threshold": 0.10, "ratio": 0.50, "desc": "浮盈 10% 减半"}
        ],
        "SIDEWAYS": [
            {"threshold": 0.03, "ratio": 0.50, "desc": "浮盈 3% 减半"}
        ],
        "BEAR": [
            {"threshold": 0.02, "ratio": 1.00, "desc": "浮盈 2% 全走"}
        ],
        "CHOPPY_BEAR": [
            {"threshold": 0.02, "ratio": 0.33, "desc": "浮盈 2% 减 1/3"},
            {"threshold": 0.04, "ratio": 1.00, "desc": "浮盈 4% 全走"}
        ],
        "CRASH": []
    })

    base_holding_period: int = 20
    max_holding_days: Dict[str, int] = field(default_factory=lambda: {
        # ATOS11 v1: BULL延长持仓（让趋势赢钱）
        "BULL": 30, "SIDEWAYS": 12, "BEAR": 6, "CRASH": 1, "CHOPPY_BEAR": 6
    })

    top_n_stocks: Dict[str, int] = field(default_factory=lambda: {
        # ATOS11 v1: 增加持仓只数（更多交易机会）
        "BULL": 15, "SIDEWAYS": 10, "BEAR": 8, "CRASH": 0, "CHOPPY_BEAR": 8,
    })
    factor_lookback: int = 120

    open_threshold_by_regime: Dict[str, float] = field(default_factory=lambda: {
        "BULL": 0.70, "SIDEWAYS": 0.60, "BEAR": 0.75, "CHOPPY_BEAR": 0.75,
    })

    choppy_bear_grace_days: int = 3
    choppy_bear_score_th: int = 3
    choppy_bear_max_pos: float = 0.20
    choppy_bear_holding_days: int = 5
    choppy_bear_profit_1: float = 0.03
    choppy_bear_profit_2: float = 0.05
    choppy_bear_rebound_th: float = 0.05
    choppy_bear_volume_th: float = 1.5

    single_stock_loss_limit: float = -0.03
    daily_loss_limit: float = -0.02
    monthly_loss_limit: float = -0.05
    quarterly_loss_limit: float = -0.10
    yearly_loss_limit: float = -0.15

    market_breadth: float = 1.0
    rolling_winrate_20d: float = 0.5
    realized_vol_20d: float = 0.15

    single_cap_max: Dict[str, float] = field(default_factory=lambda: {
        # ATOS11 v1: 提高单只上限
        "BULL": 0.20, "SIDEWAYS": 0.12, "BEAR": 0.08, "CRASH": 0.00, "CHOPPY_BEAR": 0.06,
    })
    single_cap_safety_factor: float = 0.9

    style_exposure: Dict[str, float] = field(default_factory=lambda: {
        "large_cap": 0.6, "mid_cap": 0.3, "small_cap": 0.1
    })

    factor_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # ATOS2 v1 新增
    kelly_multiplier: float = 0.0  # 凯利乘数，0=禁用，0.5=half-kelly
    drawdown_step_enabled: bool = True  # 是否启用回撤阶梯
    liquidity_filter_enabled: bool = False  # 中证 1000 流动性过滤

    # ATOS2 v2 新增
    adx_bull_threshold: float = 0.0  # BULL 状态 ADX/50 阈值（0=禁用）
    rsi_bear_threshold: float = 100.0  # BEAR 状态 RSI 阈值（100=禁用）

    # ATOS6 v1 新增：防御+反应型策略
    crash_volume_spike: float = 2.0  # CRASH 触发：成交额/20日均 > 此值（恐慌盘）
    crash_grace_days: int = 5  # CRASH 后 N 天不抄底
    oversold_bounce_enabled: bool = True  # 情绪超跌反弹信号
    range_oscillation_enabled: bool = True  # 横盘震荡信号
    pullback_buy_enabled: bool = True  # 牛市回调买入
    ic_weighted: bool = False  # IC 加权选股开关
    ic_min_threshold: float = 0.02  # IC 过滤阈值
    ic_lookback_days: int = 120  # IC 回溯期
    adaptive_kelly_enabled: bool = True  # 自适应 Kelly 开关
    kelly_adaptive_high: float = 1.5  # 胜率≥60% 时凯利乘数倍数
    kelly_adaptive_low: float = 0.5  # 胜率<40% 时凯利乘数倍数
    per_universe_overrides: Dict[str, Dict] = field(default_factory=dict)  # per-universe 参数

    def get_universe_overrides(self, universe: str) -> Dict:
        """ATOS4 v1: 获取指定 universe 的参数覆盖"""
        return self.per_universe_overrides.get(universe, {})

    def effective_param(self, universe: str, param_name: str, default):
        """ATOS4 v1: 优先返回 per-universe 参数，否则返回全局默认"""
        overrides = self.get_universe_overrides(universe)
        return overrides.get(param_name, default)

    random_seed: int = 42
    log_level: str = "INFO"
    benchmark_name: str = "hs300"

    def to_dict(self) -> dict:
        result = {}
        for k, v in self.__dict__.items():
            if not k.startswith("_") and not callable(v):
                result[k] = v
        return result

    def update(self, **kwargs):
        logger = logging.getLogger("atos.config")
        audit = getattr(self, "_audit_log", [])

        for k, v in kwargs.items():
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
                    logger.info(f"Config update: {k} = {old_value} -> {v}")
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
                logger.info(f"Config update: {k} = {old_value} -> {v}")
            else:
                raise AttributeError(f"Unknown config key: {k}")

        self._audit_log = audit

    def get_audit_log(self):
        return getattr(self, "_audit_log", [])

    def effective_single_cap(self, regime: str) -> float:
        configured = self.single_cap_max.get(regime, 0.10)
        if isinstance(self.top_n_stocks, dict):
            target_n = self.top_n_stocks.get(regime, 8)
        else:
            target_n = self.top_n_stocks if self.top_n_stocks > 0 else 8
        total_cap = self.base_position.get(regime, 0.5)
        derived_cap = total_cap / max(target_n, 1) * self.single_cap_safety_factor
        return min(configured, derived_cap)

    @classmethod
    def from_yaml(cls, path: str, validate: bool = True) -> "StrategyConfig":
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in (data or {}).items() if k in valid_keys}
        config = cls(**filtered)
        if validate:
            from .validator import validate_config
            errors = validate_config(config)
            if errors:
                raise ValueError(
                    f"Config validation failed ({len(errors)} errors):\n"
                    + "\n".join(f"  - {e}" for e in errors)
                )
        return config

    def to_yaml(self, path: str):
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)
