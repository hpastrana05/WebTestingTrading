from fastapi import APIRouter, HTTPException

from app.schemas import (
    AlertRequest,
    AlertRule,
    AlertRuleUpdate,
    BacktestRequest,
    BacktestResult,
    StrategyConfig,
    StrategyConfigUpdate,
    StrategyInfo,
    TuningRequest,
    TuningResult,
)
from app.services import storage
from app.services.alerts import check_alert_rules
from app.services.backtester import run_backtest
from app.services.indicator_catalog import INDICATOR_CATALOG, OPERATORS, PRICE_FIELDS
from app.services.market_data import fetch_ohlcv
from app.services.telegram_bot import send_telegram_message
from app.services.tuner import run_tuning
from app.strategies import get_strategy, list_builtin_strategies
from app.strategies.config_strategy import ConfigStrategy

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


# --- Indicator catalog (pandas-ta) ---

@router.get("/indicators")
def get_indicators():
    return {
        "indicators": INDICATOR_CATALOG,
        "operators": OPERATORS,
        "price_fields": PRICE_FIELDS,
    }


# --- Strategies (builtin + custom) ---

@router.get("/strategies", response_model=list[StrategyInfo])
def get_strategies():
    items: list[StrategyInfo] = []
    for s in list_builtin_strategies():
        items.append(
            StrategyInfo(
                id=s.id,
                name=s.name,
                description=s.description,
                parameters=s.parameters,
                source="builtin",
            )
        )
    for config in storage.list_strategy_configs():
        items.append(
            StrategyInfo(
                id=config.id or "",
                name=config.name,
                description=f"Custom · {config.yahoo_ticker} · {config.interval}",
                parameters={},
                source="custom",
            )
        )
    return items


@router.get("/strategies/configs/all", response_model=list[StrategyConfig])
def get_strategy_configs():
    return storage.list_strategy_configs()


@router.get("/strategies/configs/{strategy_id}", response_model=StrategyConfig)
def get_one_strategy_config(strategy_id: str):
    try:
        return storage.get_strategy_config(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/strategies/configs", response_model=StrategyConfig)
def create_strategy_config(config: StrategyConfig):
    return storage.create_strategy_config(config)


@router.put("/strategies/configs/{strategy_id}", response_model=StrategyConfig)
def put_strategy_config(strategy_id: str, update: StrategyConfigUpdate):
    try:
        return storage.update_strategy_config(strategy_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/strategies/configs/{strategy_id}")
def remove_strategy_config(strategy_id: str):
    try:
        storage.delete_strategy_config(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/strategies/{strategy_id}", response_model=StrategyInfo)
def get_strategy_detail(strategy_id: str):
    try:
        s = get_strategy(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    source = "custom" if isinstance(s, ConfigStrategy) else "builtin"
    return StrategyInfo(
        id=s.id,
        name=s.name,
        description=s.description,
        parameters=s.parameters,
        source=source,
    )


# --- Backtest ---

@router.post("/backtest", response_model=BacktestResult)
def backtest(request: BacktestRequest):
    try:
        strategy = get_strategy(request.strategy_id)
        symbol = request.symbol
        period = request.period
        interval = request.interval

        # Custom strategies carry their own default market settings
        if isinstance(strategy, ConfigStrategy):
            symbol = symbol or strategy.config.yahoo_ticker
            period = period or strategy.config.period
            interval = interval or strategy.config.interval

        symbol = symbol or "AAPL"
        period = period or "1y"
        interval = interval or "1d"

        data = fetch_ohlcv(symbol, period, interval)
        return run_backtest(
            strategy=strategy,
            data=data,
            parameters=request.parameters,
            initial_cash=request.initial_cash,
            symbol=symbol,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Parameter tuning ---

@router.post("/tuning", response_model=TuningResult)
def tuning(request: TuningRequest):
    try:
        return run_tuning(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Alerts / Telegram ---

@router.post("/alerts/send")
async def send_alert(request: AlertRequest):
    result = await send_telegram_message(request.message)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("detail", "Send failed"))
    return result


@router.get("/alerts/rules", response_model=list[AlertRule])
def get_alert_rules():
    return storage.list_alert_rules()


@router.post("/alerts/rules", response_model=AlertRule)
def create_alert_rule(rule: AlertRule):
    try:
        get_strategy(rule.strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return storage.create_alert_rule(rule)


@router.patch("/alerts/rules/{rule_id}", response_model=AlertRule)
def patch_alert_rule(rule_id: str, update: AlertRuleUpdate):
    try:
        if update.strategy_id is not None:
            get_strategy(update.strategy_id)
        return storage.update_alert_rule(rule_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/alerts/rules/{rule_id}")
def remove_alert_rule(rule_id: str):
    try:
        storage.delete_alert_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/alerts/check")
async def check_alerts():
    """Evaluate saved rules and notify on entry/exit flips."""
    return {"results": await check_alert_rules()}
