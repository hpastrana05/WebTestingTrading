import pandas as pd

from app.schemas import AlertRule
from app.services import storage
from app.services.market_data import fetch_ohlcv
from app.services.telegram_bot import format_signal_alert, send_telegram_message
from app.strategies import get_strategy


async def check_alert_rules() -> list[dict]:
    """
    Evaluate enabled rules on recent daily data.
    Sends Telegram messages when the latest bar flips into/out of a position.
    """
    results: list[dict] = []
    rules = [r for r in storage.list_alert_rules() if r.enabled]

    for rule in rules:
        try:
            event = await _evaluate_rule(rule)
            results.append(event)
        except Exception as exc:
            results.append({"rule_id": rule.id, "ok": False, "detail": str(exc)})

    return results


async def _evaluate_rule(rule: AlertRule) -> dict:
    from app.strategies.config_strategy import ConfigStrategy

    strategy = get_strategy(rule.strategy_id)
    period = "3mo"
    interval = "1d"
    if isinstance(strategy, ConfigStrategy):
        interval = strategy.config.interval or interval
    data = fetch_ohlcv(rule.symbol, period=period, interval=interval)
    signals = strategy.generate_signals(data, rule.parameters)

    if len(signals) < 2:
        return {"rule_id": rule.id, "ok": True, "event": "insufficient_data"}

    prev_signal = int(signals.iloc[-2])
    last_signal = int(signals.iloc[-1])
    last_price = float(data["Close"].iloc[-1])
    last_date = pd.Timestamp(data.index[-1]).strftime("%Y-%m-%d")

    side = None
    if prev_signal == 0 and last_signal == 1 and "entry" in rule.notify_on:
        side = "entry"
    elif prev_signal == 1 and last_signal == 0 and "exit" in rule.notify_on:
        side = "exit"

    if side is None:
        return {
            "rule_id": rule.id,
            "ok": True,
            "event": "none",
            "signal": last_signal,
            "date": last_date,
        }

    text = format_signal_alert(
        symbol=rule.symbol,
        strategy_id=rule.strategy_id,
        side=side,
        price=last_price,
        extra=f"Rule: {rule.name}\nDate: {last_date}",
    )
    send_result = await send_telegram_message(text)
    return {
        "rule_id": rule.id,
        "ok": bool(send_result.get("ok")),
        "event": side,
        "telegram": send_result,
        "date": last_date,
        "price": last_price,
    }
