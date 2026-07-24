from app.services import storage
from app.strategies.base import Strategy
from app.strategies.config_strategy import ConfigStrategy
from app.strategies.oro_swing_adaptive import OroSwingAdaptive
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossover
from app.strategies.vwap_momentum import VwapMomentum

# Built-in Python strategies
_BUILTINS: dict[str, Strategy] = {
    strategy.id: strategy
    for strategy in (SmaCrossover(), RsiStrategy(), VwapMomentum(), OroSwingAdaptive())
}


def get_strategy(strategy_id: str) -> Strategy:
    if strategy_id in _BUILTINS:
        return _BUILTINS[strategy_id]
    # Generated Python strategies (from Pine import)
    try:
        from app.services.generated_strategies import get_generated_strategy

        return get_generated_strategy(strategy_id)
    except KeyError:
        pass
    try:
        config = storage.get_strategy_config(strategy_id)
        return ConfigStrategy(config)
    except KeyError as exc:
        raise KeyError(f"Unknown strategy: {strategy_id}") from exc


def list_strategies() -> list[Strategy]:
    from app.services.generated_strategies import list_generated_strategies

    items: list[Strategy] = list(_BUILTINS.values())
    items.extend(list_generated_strategies())
    for config in storage.list_strategy_configs():
        items.append(ConfigStrategy(config))
    return items


def list_builtin_strategies() -> list[Strategy]:
    from app.services.generated_strategies import list_generated_strategies

    return list(_BUILTINS.values()) + list_generated_strategies()
