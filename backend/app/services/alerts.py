import math

import pandas as pd

from app.schemas import AlertRule
from app.services import storage
from app.services.market_data import fetch_ohlcv
from app.services.telegram_bot import format_signal_alert, send_telegram_message
from app.strategies import get_strategy
from app.strategies.base import Strategy


def _default_period_for_interval(interval: str) -> str:
    """Pick a Yahoo lookback that usually works for the candle size."""
    if interval in ("1m", "2m"):
        return "5d"
    if interval in ("5m", "15m", "30m"):
        return "1mo"
    if interval in ("60m", "90m", "1h"):
        return "3mo"
    if interval in ("5d", "1wk", "1mo", "3mo"):
        return "2y"
    return "3mo"


def _fmt_price(value: float | None) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    return f"{float(value):.4f}"


def _fmt_stamp(ts, interval: str) -> str:
    stamp = pd.Timestamp(ts)
    if interval in ("1d", "5d", "1wk", "1mo", "3mo"):
        return stamp.strftime("%Y-%m-%d")
    return stamp.strftime("%Y-%m-%d %H:%M")


def resolve_alert_rule(ref: str | None = None) -> tuple[int, AlertRule]:
    """
    Resolve a rule by 1-based list index (`1`), UUID/prefix, or name substring.
    If ref is empty and there is exactly one rule, that rule is returned.
    Returns (index, rule). Raises KeyError / ValueError on miss.
    """
    rules = storage.list_alert_rules()
    if not rules:
        raise KeyError("No hay reglas de alerta")

    token = (ref or "").strip()
    if not token:
        if len(rules) == 1:
            return 1, rules[0]
        raise ValueError(
            "Indica el número, id o nombre de la regla.\n"
            f"Hay {len(rules)} reglas — usa /list"
        )

    if token.isdigit():
        idx = int(token)
        if idx < 1 or idx > len(rules):
            raise KeyError(f"Índice fuera de rango (1–{len(rules)})")
        return idx, rules[idx - 1]

    # UUID / prefix
    id_matches = [(i + 1, r) for i, r in enumerate(rules) if r.id and r.id.startswith(token)]
    if len(id_matches) == 1:
        return id_matches[0]
    if len(id_matches) > 1:
        raise ValueError(f"Id ambiguo '{token}' — usa más caracteres o el número de /list")

    # Name (case-insensitive substring)
    needle = token.casefold()
    name_matches = [
        (i + 1, r) for i, r in enumerate(rules) if needle in (r.name or "").casefold()
    ]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        lines = ", ".join(f"#{i} {r.name}" for i, r in name_matches[:5])
        raise ValueError(f"Nombre ambiguo '{token}': {lines}")

    raise KeyError(f"Regla no encontrada: {token}")


def signal_label(signal: int) -> str:
    if signal == 1:
        return "LONG"
    if signal == -1:
        return "SHORT"
    return "FLAT"


def peek_rule_state(rule: AlertRule) -> dict:
    """Read current signal/price for a rule without sending Telegram messages."""
    snapshot = _load_rule_snapshot(rule)
    if snapshot.get("insufficient"):
        return {
            "ok": True,
            "rule_id": rule.id,
            "name": rule.name,
            "symbol": rule.symbol,
            "enabled": rule.enabled,
            "interval": snapshot["interval"],
            "period": snapshot["period"],
            "strategy_id": rule.strategy_id,
            "strategy_name": snapshot["strategy_name"],
            "event": "insufficient_data",
            "signal": None,
            "side": "—",
            "price": None,
            "date": None,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "pending_events": [],
        }

    signals = snapshot["signals"]
    data = snapshot["data"]
    strategy = snapshot["strategy"]
    params = snapshot["params"]
    interval = snapshot["interval"]
    prev_signal = int(signals.iloc[-2])
    last_signal = int(signals.iloc[-1])
    last_price = float(data["Close"].iloc[-1])
    last_date = _fmt_stamp(data.index[-1], interval)

    frame = _safe_signal_frame(strategy, data, params)
    entry_idx = None
    stop = take = entry_price = None
    if last_signal != 0:
        entry_idx = _find_entry_index(signals, last_signal, len(signals) - 1)
        if entry_idx is not None:
            entry_price = float(data["Close"].iloc[entry_idx])
            stop, take = _levels_for_new_entry(frame, last_signal, len(signals) - 1)
            if stop is None and take is None:
                stop, take = _levels_at_entry(frame, entry_idx)

    pending = _detect_events(prev_signal, last_signal, rule.notify_on)
    return {
        "ok": True,
        "rule_id": rule.id,
        "name": rule.name,
        "symbol": rule.symbol,
        "enabled": rule.enabled,
        "interval": interval,
        "period": snapshot["period"],
        "strategy_id": rule.strategy_id,
        "strategy_name": snapshot["strategy_name"],
        "event": "ok",
        "signal": last_signal,
        "side": signal_label(last_signal),
        "prev_signal": prev_signal,
        "price": last_price,
        "date": last_date,
        "entry_price": entry_price,
        "stop_loss": stop,
        "take_profit": take,
        "pending_events": pending,
        "notify_on": list(rule.notify_on or ["entry", "exit"]),
    }


async def check_alert_rules() -> list[dict]:
    """
    Evaluate enabled rules on recent OHLCV for each rule's interval.
    Sends Telegram messages on trade entry and exit (and flips).
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


def _detect_events(prev_signal: int, last_signal: int, notify_on: list[str] | None) -> list[str]:
    notify = set(notify_on or [])
    if not notify:
        notify = {"entry", "exit"}
    notify_entry = "entry" in notify
    notify_exit = "exit" in notify

    events: list[str] = []
    if prev_signal == 0 and last_signal != 0 and notify_entry:
        events.append("long_entry" if last_signal == 1 else "short_entry")
    elif prev_signal != 0 and last_signal == 0 and notify_exit:
        events.append("long_exit" if prev_signal == 1 else "short_exit")
    elif prev_signal != 0 and last_signal != 0 and prev_signal != last_signal:
        if notify_exit:
            events.append("long_exit" if prev_signal == 1 else "short_exit")
        if notify_entry:
            events.append("long_entry" if last_signal == 1 else "short_entry")
    return events


def _load_rule_snapshot(rule: AlertRule) -> dict:
    from app.strategies.config_strategy import ConfigStrategy

    strategy = get_strategy(rule.strategy_id)
    interval = (rule.interval or "").strip() or "1d"
    period = (rule.period or "").strip()
    if not period:
        if isinstance(strategy, ConfigStrategy):
            period = strategy.config.period or _default_period_for_interval(interval)
            if not rule.interval and strategy.config.interval:
                interval = strategy.config.interval
        else:
            period = _default_period_for_interval(interval)

    data = fetch_ohlcv(rule.symbol, period=period, interval=interval)
    params = rule.parameters or {}
    signals = strategy.generate_signals(data, params)
    strategy_name = getattr(strategy, "name", None) or rule.strategy_id

    if len(signals) < 2:
        return {
            "insufficient": True,
            "interval": interval,
            "period": period,
            "strategy": strategy,
            "strategy_name": strategy_name,
            "data": data,
            "signals": signals,
            "params": params,
        }

    return {
        "insufficient": False,
        "interval": interval,
        "period": period,
        "strategy": strategy,
        "strategy_name": strategy_name,
        "data": data,
        "signals": signals,
        "params": params,
    }


async def _evaluate_rule(rule: AlertRule) -> dict:
    snapshot = _load_rule_snapshot(rule)
    interval = snapshot["interval"]
    period = snapshot["period"]

    if snapshot.get("insufficient"):
        return {
            "rule_id": rule.id,
            "ok": True,
            "event": "insufficient_data",
            "interval": interval,
            "period": period,
        }

    signals = snapshot["signals"]
    data = snapshot["data"]
    strategy = snapshot["strategy"]
    params = snapshot["params"]

    prev_signal = int(signals.iloc[-2])
    last_signal = int(signals.iloc[-1])
    last_price = float(data["Close"].iloc[-1])
    last_date = _fmt_stamp(data.index[-1], interval)
    events = _detect_events(prev_signal, last_signal, rule.notify_on)

    if not events:
        return {
            "rule_id": rule.id,
            "ok": True,
            "event": "none",
            "signal": last_signal,
            "date": last_date,
            "interval": interval,
            "period": period,
        }

    # Dedupe: same bar + same transition must not spam on every poll
    bar_key = str(data.index[-1])
    fingerprint = f"{bar_key}|{prev_signal}->{last_signal}|{','.join(events)}"
    if rule.id:
        known = storage.get_alert_notify_fingerprints().get(rule.id)
        if known == fingerprint:
            return {
                "rule_id": rule.id,
                "ok": True,
                "event": "already_sent",
                "events": events,
                "signal": last_signal,
                "date": last_date,
                "interval": interval,
                "period": period,
            }

    frame = _safe_signal_frame(strategy, data, params)
    ctx = _build_trade_context(
        data=data,
        signals=signals,
        frame=frame,
        prev_signal=prev_signal,
        last_signal=last_signal,
    )

    telegrams: list[dict] = []
    for event in events:
        payload = _payload_for_event(event, ctx, last_price)
        text = format_signal_alert(
            alert_type=payload["alert_type"],
            ticker=rule.symbol,
            timeframe=interval,
            side=payload["side"],
            strategy_name=snapshot["strategy_name"],
            current_price=payload["current_price"],
            entry_price=payload.get("entry_price"),
            exit_price=payload.get("exit_price"),
            stop_loss=payload.get("stop_loss"),
            take_profit=payload.get("take_profit"),
            trigger_reason=payload["trigger_reason"],
            status=payload["status"],
            timestamp=last_date,
            rule_name=rule.name,
        )
        send_result = await send_telegram_message(text)
        telegrams.append({"event": event, **send_result})

    ok = all(bool(t.get("ok")) for t in telegrams)
    if ok and rule.id:
        storage.set_alert_notify_fingerprint(rule.id, fingerprint)

    return {
        "rule_id": rule.id,
        "ok": ok,
        "event": events[0] if len(events) == 1 else "flip",
        "events": events,
        "telegram": telegrams,
        "date": last_date,
        "price": last_price,
        "interval": interval,
        "period": period,
    }


def _safe_signal_frame(strategy: Strategy, data: pd.DataFrame, params: dict) -> pd.DataFrame | None:
    try:
        return strategy.generate_signal_frame(data, params)
    except Exception:
        return None


def _find_entry_index(signals: pd.Series, side: int, end_idx: int) -> int | None:
    """Last bar where `side` position started, looking back from end_idx inclusive."""
    if side == 0 or end_idx < 0:
        return None
    j = end_idx
    while j >= 0 and int(signals.iloc[j]) == side:
        j -= 1
    start = j + 1
    return start if start <= end_idx and int(signals.iloc[start]) == side else None


def _levels_at_entry(frame: pd.DataFrame | None, entry_idx: int) -> tuple[float | None, float | None]:
    if frame is None or entry_idx is None or entry_idx < 0:
        return None, None
    stop = take = None
    if "stop" in frame.columns and pd.notna(frame["stop"].iloc[entry_idx]):
        stop = float(frame["stop"].iloc[entry_idx])
    if "take" in frame.columns and pd.notna(frame["take"].iloc[entry_idx]):
        take = float(frame["take"].iloc[entry_idx])
    # Look back for the bar where the strategy actually stamped entry + levels
    if (stop is None or take is None) and "entry" in frame.columns and "stop" in frame.columns:
        for k in range(entry_idx, max(-1, entry_idx - 20), -1):
            if int(frame["entry"].iloc[k]) == 0:
                continue
            if stop is None and pd.notna(frame["stop"].iloc[k]):
                stop = float(frame["stop"].iloc[k])
            if take is None and "take" in frame.columns and pd.notna(frame["take"].iloc[k]):
                take = float(frame["take"].iloc[k])
            if stop is not None and take is not None:
                break
    return stop, take


def _levels_for_new_entry(
    frame: pd.DataFrame | None,
    side: int,
    end_idx: int,
) -> tuple[float | None, float | None]:
    """Prefer the last frame entry matching `side` (with stop/take)."""
    if frame is None or side == 0 or end_idx < 0:
        return None, None
    if "entry" in frame.columns:
        for k in range(end_idx, max(-1, end_idx - 20), -1):
            if int(frame["entry"].iloc[k]) != side:
                continue
            stop = take = None
            if "stop" in frame.columns and pd.notna(frame["stop"].iloc[k]):
                stop = float(frame["stop"].iloc[k])
            if "take" in frame.columns and pd.notna(frame["take"].iloc[k]):
                take = float(frame["take"].iloc[k])
            if stop is not None or take is not None:
                return stop, take
    return _levels_at_entry(frame, end_idx)


def _build_trade_context(
    data: pd.DataFrame,
    signals: pd.Series,
    frame: pd.DataFrame | None,
    prev_signal: int,
    last_signal: int,
) -> dict:
    """Infer entry/SL/TP/exit reason around the latest signal change."""
    close = data["Close"].astype(float)
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    i = len(signals) - 1

    # Position that just opened or that just closed
    if prev_signal == 0 and last_signal != 0:
        entry_idx = i
        held_side = last_signal
    elif prev_signal != 0 and last_signal == 0:
        entry_idx = _find_entry_index(signals, prev_signal, i - 1)
        held_side = prev_signal
    else:
        # flip: previous side closed on this bar conceptually
        entry_idx = _find_entry_index(signals, prev_signal, i - 1)
        held_side = prev_signal

    entry_price = float(close.iloc[entry_idx]) if entry_idx is not None else None
    stop, take = _levels_at_entry(frame, entry_idx if entry_idx is not None else -1)

    flat_reason = ""
    if frame is not None and "force_flat" in frame.columns and bool(frame["force_flat"].iloc[i]):
        flat_reason = str(frame["flat_reason"].iloc[i] or "") if "flat_reason" in frame.columns else ""

    exit_price = None
    exit_reason = "Señal de salida"
    if prev_signal != 0 and (last_signal == 0 or last_signal != prev_signal):
        hi = float(high.iloc[i])
        lo = float(low.iloc[i])
        px = float(close.iloc[i])
        if held_side == 1:
            if stop is not None and lo <= stop:
                exit_price, exit_reason = stop, "Stop loss (SL)"
            elif take is not None and hi >= take:
                exit_price, exit_reason = take, "Take profit (TP)"
            else:
                exit_price, exit_reason = px, flat_reason or "Señal de salida"
        else:
            if stop is not None and hi >= stop:
                exit_price, exit_reason = stop, "Stop loss (SL)"
            elif take is not None and lo <= take:
                exit_price, exit_reason = take, "Take profit (TP)"
            else:
                exit_price, exit_reason = px, flat_reason or "Señal de salida"
        if flat_reason == "Session":
            exit_reason = "Cierre de sesión"

    # For a brand-new entry after a flip, refresh SL/TP from the new entry bar
    new_entry_stop = new_entry_take = None
    if last_signal != 0 and (prev_signal == 0 or prev_signal != last_signal):
        new_entry_stop, new_entry_take = _levels_for_new_entry(frame, last_signal, i)

    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stop": stop,
        "take": take,
        "new_entry_price": float(close.iloc[i]) if last_signal != 0 else None,
        "new_entry_stop": new_entry_stop,
        "new_entry_take": new_entry_take,
        "exit_reason": exit_reason,
        "last_price": float(close.iloc[i]),
    }


def _payload_for_event(event: str, ctx: dict, last_price: float) -> dict:
    is_entry = event.endswith("_entry")
    is_long = "long" in event
    side = "LONG" if is_long else "SHORT"

    if is_entry:
        return {
            "alert_type": "ENTRADA",
            "side": side,
            "current_price": last_price,
            "entry_price": ctx.get("new_entry_price") or last_price,
            "exit_price": None,
            "stop_loss": ctx.get("new_entry_stop")
            if ctx.get("new_entry_stop") is not None
            else ctx.get("stop"),
            "take_profit": ctx.get("new_entry_take")
            if ctx.get("new_entry_take") is not None
            else ctx.get("take"),
            "trigger_reason": "Señal de entrada",
            "status": "ABIERTA",
        }

    return {
        "alert_type": "SALIDA",
        "side": side,
        "current_price": last_price,
        "entry_price": ctx.get("entry_price"),
        "exit_price": ctx.get("exit_price") or last_price,
        "stop_loss": ctx.get("stop"),
        "take_profit": ctx.get("take"),
        "trigger_reason": ctx.get("exit_reason") or "Señal de salida",
        "status": "CERRADA",
    }
