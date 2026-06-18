"""参数扰动测试"""
from copy import deepcopy

import numpy as np
import pandas as pd

from .engine import BacktestEngine


def _get_nested_value(obj, dotted_key: str):
    parts = dotted_key.split(".")
    value = obj
    for part in parts:
        value = getattr(value, part) if not isinstance(value, dict) else value[part]
    return value


def _set_nested_value(obj, dotted_key: str, value):
    parts = dotted_key.split(".")
    target = obj
    for part in parts[:-1]:
        target = getattr(target, part) if not isinstance(target, dict) else target[part]
    final_key = parts[-1]
    if isinstance(target, dict):
        target[final_key] = value
    else:
        setattr(target, final_key, value)


def parameter_perturbation(base_config,
                            df: pd.DataFrame,
                            params_to_test=None,
                            perturbation: float = 0.2,
                            n_trials: int = 30,
                            random_seed: int = 42) -> pd.DataFrame:
    """参数扰动测试（支持嵌套键、可复现、除零保护）"""
    np.random.seed(random_seed)

    if params_to_test is None:
        params_to_test = []
        base_dict = base_config.to_dict() if hasattr(base_config, "to_dict") else vars(base_config)
        for k, v in base_dict.items():
            if isinstance(v, (int, float)):
                params_to_test.append(k)
            elif isinstance(v, dict):
                for sub_k in v:
                    if isinstance(v[sub_k], (int, float)):
                        params_to_test.append(f"{k}.{sub_k}")

    results = []
    for param_name in params_to_test:
        base_value = _get_nested_value(base_config, param_name)
        if base_value == 0:
            continue
        for trial in range(n_trials):
            perturbed = base_value * (1 + np.random.uniform(-perturbation, perturbation))
            test_config = deepcopy(base_config)
            _set_nested_value(test_config, param_name, perturbed)

            try:
                engine = BacktestEngine(test_config)
                result = engine.run(df)
                ratio = (perturbed / base_value - 1) if base_value != 0 else 0
                results.append({
                    "param": param_name,
                    "trial": trial,
                    "base_value": base_value,
                    "perturbed_value": perturbed,
                    "ratio": ratio,
                    **result.metrics,
                })
            except Exception as e:
                continue

    return pd.DataFrame(results)
