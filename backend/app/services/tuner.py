from itertools import product

from app.schemas import TuningRequest, TuningResult, TuningTrial
from app.services.backtester import run_backtest
from app.services.market_data import fetch_ohlcv
from app.strategies import get_strategy


def run_tuning(request: TuningRequest) -> TuningResult:
    """Grid-search strategy parameters and rank by a simple metric."""
    strategy = get_strategy(request.strategy_id)
    data = fetch_ohlcv(request.symbol, request.period, request.interval)

    # Build grid from request, falling back to strategy defaults only
    keys = list(request.param_grid.keys())
    if not keys:
        raise ValueError("param_grid must include at least one parameter list")

    value_lists = [request.param_grid[k] for k in keys]
    trials: list[TuningTrial] = []

    for combo in product(*value_lists):
        params = dict(zip(keys, combo))
        # Fill remaining params with defaults
        full_params = strategy.resolve_params(params)
        try:
            result = run_backtest(
                strategy=strategy,
                data=data,
                parameters=full_params,
                initial_cash=request.initial_cash,
                symbol=request.symbol,
                interval=request.interval,
                position_size_pct=request.position_size_pct,
                commission_pct=request.commission_pct,
                risk_percent=request.risk_percent,
                slippage=request.slippage,
                fill_on=request.fill_on,
            )
        except ValueError:
            # Skip invalid combinations (e.g. fast >= slow)
            continue

        score = getattr(result, request.metric, None)
        if score is None:
            raise ValueError(f"Unknown metric: {request.metric}")

        trials.append(
            TuningTrial(
                parameters=full_params,
                total_return_pct=result.total_return_pct,
                final_equity=result.final_equity,
                num_trades=result.num_trades,
            )
        )

    if not trials:
        raise ValueError("No valid parameter combinations to evaluate")

    # Rank by chosen metric (currently only total_return_pct is used in trials)
    trials.sort(key=lambda t: t.total_return_pct, reverse=True)
    best = trials[0]

    return TuningResult(
        strategy_id=request.strategy_id,
        symbol=request.symbol,
        metric=request.metric,
        best_parameters=best.parameters,
        best_score=best.total_return_pct,
        trials=trials,
    )
