"""config 模块"""
from .strategy_config import StrategyConfig
from .validator import validate_config


def load_config(path: str = "config/params.yaml") -> StrategyConfig:
    return StrategyConfig.from_yaml(path)


def save_config(config, path: str = "config/params.yaml"):
    config.to_yaml(path)


__all__ = ["StrategyConfig", "validate_config", "load_config", "save_config"]
