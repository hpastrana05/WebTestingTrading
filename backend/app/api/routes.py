from fastapi import APIRouter, HTTPException

from app.schemas import (
    AlertRequest,
    AlertRule,
    AlertRuleUpdate,
    BacktestRequest,
    BacktestResult,
    PineImportRequest,
    PineImportResult,
    PineSavePythonResult,
    GeneratedRenameRequest,
    TelegramChat,
    TelegramChatCreate,
    TelegramChatUpdate,
    StrategyConfig,
    StrategyConfigUpdate,
    StrategyInfo,
    TuningRequest,
    TuningResult,
)
from app.services import storage
from app.services.alerts import check_alert_rules
from app.services.backtester import run_backtest
from app.services.generated_strategies import (
    delete_generated_strategy,
    rename_generated_strategy,
    save_generated_strategy,
    with_python_prefix,
)
from app.services.indicator_catalog import INDICATOR_CATALOG, OPERATORS, PRICE_FIELDS
from app.services.market_data import fetch_ohlcv
from app.services.pine_import import convert_pinescript
from app.services.pine_to_python import generate_python_strategy
from app.services.telegram_bot import send_telegram_message
from app.services.tuner import run_tuning
from app.strategies import get_strategy, list_builtin_strategies
from app.strategies.config_strategy import ConfigStrategy
from app.strategies.sma_crossover import SmaCrossover
from app.strategies.rsi import RsiStrategy
from app.strategies.vwap_momentum import VwapMomentum
from app.strategies.oro_swing_adaptive import OroSwingAdaptive

_CORE_BUILTIN_IDS = {
    SmaCrossover.id,
    RsiStrategy.id,
    VwapMomentum.id,
    OroSwingAdaptive.id,
}

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
        source = "builtin" if s.id in _CORE_BUILTIN_IDS else "generated"
        name = with_python_prefix(s.name) if source == "generated" else s.name
        items.append(
            StrategyInfo(
                id=s.id,
                name=name,
                description=s.description,
                parameters=s.parameters,
                source=source,
                direction=getattr(s, "direction", "long"),
            )
        )
    for config in storage.list_strategy_configs():
        custom = ConfigStrategy(config)
        items.append(
            StrategyInfo(
                id=config.id or "",
                name=config.name,
                description=f"Custom · {config.direction} · {config.yahoo_ticker} · {config.interval}",
                parameters=custom.parameters,
                source="custom",
                direction=config.direction,
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


@router.post("/strategies/import-pine", response_model=PineImportResult)
def import_pinescript(body: PineImportRequest):
    """Best-effort convert Pine Script into Creator draft + Python module source."""
    try:
        result = convert_pinescript(body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not import Pine Script: {exc}",
        ) from exc

    config: StrategyConfig = result["config"]
    py = generate_python_strategy(config)
    warnings = list(result["warnings"])
    return PineImportResult(
        config=config,
        warnings=warnings,
        python_code=py["python_code"],
        python_filename=py["filename"],
        strategy_id=py["strategy_id"],
        reliability=str(result.get("reliability") or "low"),
    )


@router.post("/strategies/import-pine/save-python", response_model=PineSavePythonResult)
def save_pinescript_as_python(body: PineImportRequest):
    """Convert Pine and persist a generated Python strategy (hot-loaded)."""
    try:
        result = convert_pinescript(body.code)
        path, strategy, source = save_generated_strategy(result["config"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not save Python strategy: {exc}",
        ) from exc
    return PineSavePythonResult(
        id=strategy.id,
        name=strategy.name,
        filename=path.name,
        python_code=source,
        warnings=list(result["warnings"]),
    )


@router.delete("/strategies/generated/{strategy_id}")
def remove_generated_strategy(strategy_id: str):
    try:
        delete_generated_strategy(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.patch("/strategies/generated/{strategy_id}", response_model=StrategyInfo)
def rename_generated(strategy_id: str, body: GeneratedRenameRequest):
    try:
        strategy = rename_generated_strategy(strategy_id, body.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StrategyInfo(
        id=strategy.id,
        name=with_python_prefix(strategy.name),
        description=strategy.description,
        parameters=strategy.parameters,
        source="generated",
        direction=getattr(strategy, "direction", "long"),
    )


@router.get("/strategies/{strategy_id}", response_model=StrategyInfo)
def get_strategy_detail(strategy_id: str):
    try:
        s = get_strategy(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    source = (
        "custom"
        if isinstance(s, ConfigStrategy)
        else ("generated" if str(s.id).startswith("gen_") else "builtin")
    )
    return StrategyInfo(
        id=s.id,
        name=with_python_prefix(s.name) if source == "generated" else s.name,
        description=s.description,
        parameters=s.parameters,
        source=source,
        direction=getattr(s, "direction", "long"),
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
            interval=interval,
            position_size_pct=request.position_size_pct,
            commission_pct=request.commission_pct,
            risk_percent=request.risk_percent,
            slippage=request.slippage,
            fill_on=request.fill_on,
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


# --- Telegram chat targets ---


@router.get("/telegram/chats", response_model=list[TelegramChat])
def get_telegram_chats():
    return storage.list_telegram_chats()


@router.post("/telegram/chats", response_model=TelegramChat)
def create_telegram_chat(body: TelegramChatCreate):
    try:
        return storage.create_telegram_chat(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/telegram/chats/{chat_entry_id}", response_model=TelegramChat)
def patch_telegram_chat(chat_entry_id: str, body: TelegramChatUpdate):
    try:
        return storage.update_telegram_chat(chat_entry_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/telegram/chats/{chat_entry_id}")
def delete_telegram_chat(chat_entry_id: str):
    try:
        storage.delete_telegram_chat(chat_entry_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
