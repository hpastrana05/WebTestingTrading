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
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        return {
            "ok": False,
            "detail": "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env",
        }

    try:
        # Prefer the long-polling Application bot if it's running
        if _application is not None and _application.bot is not None:
            message = await _application.bot.send_message(chat_id=chat_id, text=text)
        else:
            from telegram import Bot

            bot = Bot(token=token)
            message = await bot.send_message(chat_id=chat_id, text=text)
        return {"ok": True, "message_id": message.message_id}
    except Exception as exc:
        logger.exception("Telegram send failed")
        return {"ok": False, "detail": str(exc)}


def _price(value: float | None) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    return f"{float(value):.4f}"


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
    header = f"[{alert_type}] {ticker} · {timeframe} · {side}"
    lines = [
        header,
        "",
        f"Estrategia: {strategy_name}",
    ]
    if rule_name:
        lines.append(f"Regla: {rule_name}")
    lines.extend(
        [
            f"Precio: {_price(current_price)}",
            f"Entrada: {_price(entry_price)}",
            f"Salida: {_price(exit_price)}",
            f"SL: {_price(stop_loss)}",
            f"TP: {_price(take_profit)}",
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
    """Only accept messages from the configured chat."""
    expected = (settings.telegram_chat_id or "").strip()
    if not expected:
        return False
    chat = update.effective_chat
    if chat is None:
        return False
    return str(chat.id) == expected


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
    lines = [
        f"{header} [{flag}]",
        f"{state.get('symbol')} · {state.get('interval')} · {state.get('side')}",
        f"Estrategia: {state.get('strategy_name')}",
        f"Precio: {_price(state.get('price'))}",
        f"Entrada: {_price(state.get('entry_price'))}",
        f"SL: {_price(state.get('stop_loss'))}",
        f"TP: {_price(state.get('take_profit'))}",
        f"Barra: {state.get('date') or '—'}",
    ]
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
