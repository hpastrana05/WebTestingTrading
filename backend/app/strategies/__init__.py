from app.services import storage
from app.strategies.base import Strategy
from app.strategies.config_strategy import ConfigStrategy
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossover

# Built-in Python strategies
_BUILTINS: dict[str, Strategy] = {
    strategy.id: strategy
    for strategy in (SmaCrossover(), RsiStrategy())
}


def get_strategy(strategy_id: str) -> Strategy:
    if strategy_id in _BUILTINS:
        return _BUILTINS[strategy_id]
    try:
        config = storage.get_strategy_config(strategy_id)
        return ConfigStrategy(config)
    except KeyError as exc:
        raise KeyError(f"Unknown strategy: {strategy_id}") from exc


def list_strategies() -> list[Strategy]:
    items: list[Strategy] = list(_BUILTINS.values())
    for config in storage.list_strategy_configs():
        items.append(ConfigStrategy(config))
    return items


def list_builtin_strategies() -> list[Strategy]:
    return list(_BUILTINS.values())
