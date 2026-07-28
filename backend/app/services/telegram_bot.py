import logging
import math
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import settings
from app.schemas import AlertRule, AlertRuleUpdate
from app.services import storage

logger = logging.getLogger(__name__)

_application = None


async def send_telegram_message(text: str) -> dict:
    """Send a plain-text message via the Telegram Bot API."""
    token = settings.telegram_bot_token
    if not token:
        return {"ok": False, "detail": "TELEGRAM_BOT_TOKEN must be set in .env"}

    try:
        chats = storage.list_enabled_telegram_chats()
        if not chats:
            return {"ok": False, "detail": "No Telegram chats enabled (add in Alerts UI)"}

        sent_to: list[dict] = []
        failed_to: list[dict] = []

        # Prefer the long-polling Application bot if it's running
        app_bot = _application.bot if _application is not None else None
        bot = None
        if app_bot is None:
            from telegram import Bot

            bot = Bot(token=token)

        for c in chats:
            try:
                if app_bot is not None:
                    message = await app_bot.send_message(chat_id=c.chat_id, text=text)
                else:
                    message = await bot.send_message(chat_id=c.chat_id, text=text)  # type: ignore[union-attr]
                sent_to.append(
                    {"chat_entry_id": c.id, "chat_id": c.chat_id, "message_id": message.message_id}
                )
            except Exception as exc:
                failed_to.append({"chat_entry_id": c.id, "chat_id": c.chat_id, "detail": str(exc)})

        ok = len(sent_to) > 0
        detail = None
        if not ok:
            detail = failed_to[0].get("detail") if failed_to else "All Telegram sends failed"

        return {"ok": ok, "sent_to": sent_to, "failed_to": failed_to, "detail": detail}
    except Exception as exc:
        logger.exception("Telegram send failed")
        return {"ok": False, "detail": str(exc)}


def _price(value: float | None) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    v = float(value)
    if abs(v) >= 100:
        return f"{v:.2f}"
    if abs(v) >= 1:
        return f"{v:.4f}"
    return f"{v:.6f}"


def _delta(entry: float | None, level: float | None) -> str:
    if entry is None or level is None:
        return ""
    if any(isinstance(x, float) and (math.isnan(x) or math.isinf(x)) for x in (entry, level)):
        return ""
    d = float(level) - float(entry)
    sign = "+" if d >= 0 else ""
    # Distances read better with 2 decimals for typical FX/futures/index points
    if abs(d) >= 0.01:
        return f"  ({sign}{d:.2f} pts)"
    return f"  ({sign}{d:.6f} pts)"


def format_signal_alert(
    *,
    alert_type: str,
    ticker: str,
    timeframe: str,
    side: str,
    strategy_name: str,
    current_price: float | None,
    entry_price: float | None = None,
    exit_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trigger_reason: str = "",
    status: str = "",
    timestamp: str = "",
    rule_name: str = "",
) -> str:
    """
    Telegram body. On ENTRADA, SL/TP are the levels to place at the broker.
    """
    header = f"[{alert_type}] {ticker} · {timeframe} · {side}"
    lines = [header, "", f"Estrategia: {strategy_name}"]
    if rule_name:
        lines.append(f"Regla: {rule_name}")

    is_entry = alert_type.upper() == "ENTRADA"
    entry = entry_price if entry_price is not None else current_price

    lines.append("")
    if is_entry:
        lines.append("Niveles para el broker:")
        lines.append(f"  Entrada: {_price(entry)}")
        if stop_loss is not None:
            lines.append(f"  SL:     {_price(stop_loss)}{_delta(entry, stop_loss)}")
        else:
            lines.append("  SL:     — (la estrategia no define stop)")
        if take_profit is not None:
            lines.append(f"  TP:     {_price(take_profit)}{_delta(entry, take_profit)}")
        else:
            lines.append("  TP:     — (la estrategia no define take)")
        lines.append("")
        lines.append(f"Precio actual: {_price(current_price)}")
    else:
        lines.extend(
            [
                f"Precio: {_price(current_price)}",
                f"Entrada: {_price(entry_price)}",
                f"Salida: {_price(exit_price)}",
                f"SL: {_price(stop_loss)}{_delta(entry_price, stop_loss) if stop_loss is not None else ''}",
                f"TP: {_price(take_profit)}{_delta(entry_price, take_profit) if take_profit is not None else ''}",
            ]
        )

    lines.extend(
        [
            f"Motivo: {trigger_reason or '—'}",
            f"Estado: {status or '—'}",
            f"Hora: {timestamp or '—'}",
        ]
    )
    return "\n".join(lines)


HELP_TEXT = """Comandos del bot

/help — esta ayuda
/ping — comprobar que el bot responde
/list — lista de alertas configuradas
/show <n|id> — detalle de una alerta
/state [n|id] — estado actual (todas o una)
/check — evaluar reglas ahora (envía ENTRADA/SALIDA si hay señal)
/enable <n|id> — activar una alerta
/disable <n|id> — desactivar una alerta

Usa el número de /list (1, 2, …) o el id (o prefijo).
Ejemplos: /state 1   /disable 2   /show a1b2c3"""


def _authorized(update) -> bool:
    """Only accept messages from enabled chats configured in Alerts UI."""
    chat = update.effective_chat
    if chat is None:
        return False
    chat_id = str(chat.id)
    # Keep the env chat as a fallback authorized chat for bot administration.
    env_chat = (settings.telegram_chat_id or "").strip()
    enabled = {c.chat_id for c in storage.list_enabled_telegram_chats()}
    return chat_id == env_chat or chat_id in enabled


async def _deny_if_unauthorized(update) -> bool:
    if _authorized(update):
        return False
    # Ignore silently for other chats (don't leak that a bot exists with useful replies)
    logger.warning("Telegram command from unauthorized chat: %s", getattr(update.effective_chat, "id", None))
    return True


def _short_id(rule_id: str | None) -> str:
    if not rule_id:
        return "—"
    return rule_id[:8]


def _format_rule_line(index: int, rule: AlertRule) -> str:
    flag = "ON " if rule.enabled else "OFF"
    notify = ",".join(rule.notify_on or ["entry", "exit"])
    return (
        f"{index}. [{flag}] {rule.name}\n"
        f"   {rule.symbol} · {rule.interval} · {rule.strategy_id}\n"
        f"   id:{_short_id(rule.id)} · notify:{notify}"
    )


def _format_state_block(index: int | None, state: dict) -> str:
    flag = "ON" if state.get("enabled") else "OFF"
    header = f"#{index} {state.get('name')}" if index is not None else str(state.get("name"))
    entry = state.get("entry_price")
    stop = state.get("stop_loss")
    take = state.get("take_profit")
    lines = [
        f"{header} [{flag}]",
        f"{state.get('symbol')} · {state.get('interval')} · {state.get('side')}",
        f"Estrategia: {state.get('strategy_name')}",
        f"Precio: {_price(state.get('price'))}",
    ]
    if state.get("side") not in (None, "FLAT", "—"):
        lines.append(f"Entrada: {_price(entry)}")
        lines.append(
            f"SL: {_price(stop)}{_delta(entry, stop) if stop is not None else ''}"
            if stop is not None
            else "SL: —"
        )
        lines.append(
            f"TP: {_price(take)}{_delta(entry, take) if take is not None else ''}"
            if take is not None
            else "TP: —"
        )
    lines.append(f"Barra: {state.get('date') or '—'}")
    pending = state.get("pending_events") or []
    if pending:
        lines.append(f"Pendiente: {', '.join(pending)} (usa /check)")
    if state.get("event") == "insufficient_data":
        lines.append("Datos insuficientes para evaluar")
    return "\n".join(lines)


async def cmd_start(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    await update.message.reply_text("Bot de alertas WebTestingTrading listo.\n\n" + HELP_TEXT)


async def cmd_help(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    await update.message.reply_text(HELP_TEXT)


async def cmd_ping(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    await update.message.reply_text("pong")


async def cmd_list(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    rules = storage.list_alert_rules()
    if not rules:
        await update.message.reply_text("No hay reglas de alerta.\nCréalas en la web (Alerts).")
        return
    lines = [f"Alertas ({len(rules)}):\n"]
    for i, rule in enumerate(rules, start=1):
        lines.append(_format_rule_line(i, rule))
        lines.append("")
    lines.append("Usa /state <n> o /show <n>")
    await update.message.reply_text("\n".join(lines).rstrip())


async def cmd_show(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    from app.services.alerts import resolve_alert_rule

    if not context.args:
        await update.message.reply_text("Uso: /show <n|id>\nEjemplo: /show 1")
        return
    try:
        idx, rule = resolve_alert_rule(context.args[0])
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(str(exc))
        return

    notify = ", ".join(rule.notify_on or ["entry", "exit"])
    params = rule.parameters or {}
    param_txt = ", ".join(f"{k}={v}" for k, v in list(params.items())[:8]) or "—"
    text = "\n".join(
        [
            f"#{idx} {rule.name}",
            f"id: {rule.id}",
            f"Estado: {'activa' if rule.enabled else 'desactivada'}",
            f"Símbolo: {rule.symbol}",
            f"Timeframe: {rule.interval}",
            f"Periodo datos: {rule.period}",
            f"Estrategia: {rule.strategy_id}",
            f"Notify: {notify}",
            f"Parámetros: {param_txt}",
        ]
    )
    await update.message.reply_text(text)


async def cmd_state(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    from app.services.alerts import peek_rule_state, resolve_alert_rule

    await update.message.reply_text("Consultando estado…")

    try:
        if context.args:
            idx, rule = resolve_alert_rule(context.args[0])
            state = peek_rule_state(rule)
            text = _format_state_block(idx, state)
        else:
            rules = storage.list_alert_rules()
            if not rules:
                await update.message.reply_text("No hay reglas de alerta.")
                return
            blocks: list[str] = [f"Estado de {len(rules)} alerta(s):\n"]
            for i, rule in enumerate(rules, start=1):
                try:
                    state = peek_rule_state(rule)
                    blocks.append(_format_state_block(i, state))
                except Exception as exc:
                    blocks.append(f"#{i} {rule.name}\nError: {exc}")
                blocks.append("")
            text = "\n".join(blocks).rstrip()
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(str(exc))
        return
    except Exception as exc:
        logger.exception("cmd_state failed")
        await update.message.reply_text(f"Error: {exc}")
        return

    # Telegram hard limit ~4096
    if len(text) > 4000:
        text = text[:3990] + "\n…"
    await update.message.reply_text(text)


async def cmd_check(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    from app.services.alerts import check_alert_rules

    await update.message.reply_text("Evaluando reglas…")
    try:
        results = await check_alert_rules()
    except Exception as exc:
        logger.exception("cmd_check failed")
        await update.message.reply_text(f"Error: {exc}")
        return

    if not results:
        await update.message.reply_text("No hay reglas activas que evaluar.")
        return

    lines = [f"Check ({len(results)}):\n"]
    for row in results:
        rid = _short_id(row.get("rule_id"))
        if not row.get("ok"):
            lines.append(f"· {rid}: ERROR — {row.get('detail')}")
            continue
        event = row.get("event")
        if event in (None, "none"):
            lines.append(f"· {rid}: sin cambio (signal={row.get('signal')})")
        elif event == "already_sent":
            lines.append(f"· {rid}: ya notificado (misma transición)")
        elif event == "insufficient_data":
            lines.append(f"· {rid}: datos insuficientes")
        else:
            events = row.get("events") or [event]
            lines.append(f"· {rid}: {', '.join(events)} @ {_price(row.get('price'))}")
    await update.message.reply_text("\n".join(lines))


async def _set_enabled(update, context, enabled: bool) -> None:
    if await _deny_if_unauthorized(update):
        return
    from app.services.alerts import resolve_alert_rule

    if not context.args:
        await update.message.reply_text(f"Uso: /{'enable' if enabled else 'disable'} <n|id>")
        return
    try:
        idx, rule = resolve_alert_rule(context.args[0])
        updated = storage.update_alert_rule(rule.id, AlertRuleUpdate(enabled=enabled))
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(str(exc))
        return

    flag = "activa" if updated.enabled else "desactivada"
    await update.message.reply_text(f"#{idx} {updated.name} → {flag}")


async def cmd_enable(update, context) -> None:
    await _set_enabled(update, context, True)


async def cmd_disable(update, context) -> None:
    await _set_enabled(update, context, False)


def _build_application():
    from telegram.ext import Application, CommandHandler

    token = (settings.telegram_bot_token or "").strip()
    if not token:
        return None

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("show", cmd_show))
    app.add_handler(CommandHandler("state", cmd_state))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("enable", cmd_enable))
    app.add_handler(CommandHandler("disable", cmd_disable))
    return app


async def start_telegram_bot() -> None:
    """Start long-polling bot (call from FastAPI lifespan)."""
    global _application

    if not (settings.telegram_bot_token or "").strip():
        logger.info("Telegram bot disabled (no TELEGRAM_BOT_TOKEN)")
        return
    if not (settings.telegram_chat_id or "").strip():
        logger.warning("TELEGRAM_CHAT_ID missing — bot will ignore all commands")

    app = _build_application()
    if app is None:
        return

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    _application = app
    logger.info("Telegram bot polling started")


async def stop_telegram_bot() -> None:
    global _application
    app = _application
    _application = None
    if app is None:
        return
    try:
        if app.updater and app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
        logger.info("Telegram bot stopped")
    except Exception:
        logger.exception("Error stopping Telegram bot")


@asynccontextmanager
async def telegram_lifespan(_: object) -> AsyncIterator[None]:
    """Optional standalone lifespan helper."""
    await start_telegram_bot()
    try:
        yield
    finally:
        await stop_telegram_bot()
