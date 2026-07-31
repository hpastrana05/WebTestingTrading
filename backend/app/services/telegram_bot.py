import logging
import math
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import settings
from app.schemas import AlertRule, AlertRuleUpdate, TelegramChatUpdate
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

Alertas (reglas)
/list — lista de alertas
/show <n|id|nombre> — detalle de una alerta
/state [n|id|nombre] — estado actual (todas o una)
/check — evaluar ahora (envía ENTRADA/SALIDA si hay señal)
/enable [n…] — activar regla(s) (varios o all)
/disable [n…] — desactivar regla(s) (varios o all)

Chats Telegram
/chats — lista de chats
/chat_on <n|nombre> — activar chat (recibe alertas)
/chat_off <n|nombre> — desactivar chat (no recibe)

Otros
/help — esta ayuda
/ping — comprobar que el bot responde

Sin número, /enable /disable usan la única regla si solo hay una.
Ejemplos: /disable 1 2 3 · /disable all · /enable vwap · /chat_off 2"""


BOT_COMMANDS = [
    ("help", "Lista de comandos"),
    ("ping", "Comprobar que el bot responde"),
    ("list", "Lista de alertas (reglas)"),
    ("show", "Detalle de una alerta"),
    ("state", "Estado actual de alertas"),
    ("check", "Evaluar reglas ahora"),
    ("enable", "Activar regla(s) — varios o all"),
    ("disable", "Desactivar regla(s) — varios o all"),
    ("chats", "Lista de chats Telegram"),
    ("chat_on", "Activar un chat (recibe alertas)"),
    ("chat_off", "Desactivar un chat"),
]


def _chat_id_from_update(update) -> str | None:
    chat = update.effective_chat
    if chat is None:
        return None
    return str(chat.id)


def _is_known_chat(chat_id: str) -> bool:
    """True if chat is env fallback or listed in telegram_chats.json (even if disabled)."""
    chat_id = (chat_id or "").strip()
    env_chat = (settings.telegram_chat_id or "").strip()
    if env_chat and chat_id == env_chat:
        return True
    return any(str(c.chat_id).strip() == chat_id for c in storage.list_telegram_chats())


def _authorized(update) -> bool:
    """
    Accept commands from any configured chat (enabled or disabled).

    `enabled` on a chat only controls whether it *receives* alert broadcasts.
    Disabled chats must still be able to run /enable, /chat_on, etc.
    """
    chat_id = _chat_id_from_update(update)
    if not chat_id:
        return False
    return _is_known_chat(chat_id)


async def _deny_if_unauthorized(update) -> bool:
    if _authorized(update):
        return False
    # Ignore silently for completely unknown chats
    logger.warning(
        "Telegram command from unauthorized chat: %s",
        getattr(update.effective_chat, "id", None),
    )
    return True


def _resolve_telegram_chat(ref: str | None = None):
    """Resolve a saved Telegram chat by 1-based index or name substring."""
    chats = storage.list_telegram_chats()
    if not chats:
        raise KeyError("No hay chats configurados (añádelos en Alerts)")

    token = (ref or "").strip()
    if not token:
        if len(chats) == 1:
            return 1, chats[0]
        raise ValueError(f"Indica el número o nombre del chat (hay {len(chats)}). Usa /chats")

    if token.isdigit():
        idx = int(token)
        if idx < 1 or idx > len(chats):
            raise KeyError(f"Índice fuera de rango (1–{len(chats)})")
        return idx, chats[idx - 1]

    needle = token.casefold()
    matches = [(i + 1, c) for i, c in enumerate(chats) if needle in (c.name or "").casefold()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("Nombre ambiguo — usa el número de /chats")
    raise KeyError(f"Chat no encontrado: {token}")


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
    from app.services.alerts import resolve_alert_rules

    verb = "enable" if enabled else "disable"
    try:
        targets = resolve_alert_rules(list(context.args) if context.args else None)
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(
            f"{exc}\n\n"
            f"Uso: /{verb} [n|id|nombre]…\n"
            f"Varias: /{verb} 1 2 3\n"
            f"Todas: /{verb} all"
        )
        return

    changed: list[str] = []
    unchanged: list[str] = []
    failed: list[str] = []

    for idx, rule in targets:
        label = f"#{idx} {rule.name}"
        if not rule.id:
            failed.append(f"{label}: sin id")
            continue
        if bool(rule.enabled) == bool(enabled):
            unchanged.append(label)
            continue
        try:
            storage.update_alert_rule(rule.id, AlertRuleUpdate(enabled=enabled))
            confirmed = storage.get_alert_rule(rule.id)
            if bool(confirmed.enabled) != bool(enabled):
                failed.append(f"{label}: no se guardó")
            else:
                changed.append(label)
        except KeyError as exc:
            failed.append(f"{label}: {exc}")

    flag = "activas" if enabled else "desactivadas"
    lines: list[str] = []
    if changed:
        lines.append(f"→ {flag} ({len(changed)}):")
        lines.extend(f"  {x}" for x in changed)
    if unchanged:
        already = "ya activas" if enabled else "ya desactivadas"
        lines.append(f"{already} ({len(unchanged)}):")
        lines.extend(f"  {x}" for x in unchanged)
    if failed:
        lines.append(f"Errores ({len(failed)}):")
        lines.extend(f"  {x}" for x in failed)
    if not lines:
        lines.append("No hubo cambios.")

    await update.message.reply_text("\n".join(lines))


async def cmd_enable(update, context) -> None:
    await _set_enabled(update, context, True)


async def cmd_disable(update, context) -> None:
    await _set_enabled(update, context, False)


async def cmd_chats(update, context) -> None:
    if await _deny_if_unauthorized(update):
        return
    chats = storage.list_telegram_chats()
    if not chats:
        await update.message.reply_text(
            "No hay chats configurados.\nAñádelos en la web (Alerts → Telegram chats)."
        )
        return
    lines = [f"Chats Telegram ({len(chats)}):\n"]
    for i, c in enumerate(chats, start=1):
        flag = "ON " if c.enabled else "OFF"
        lines.append(f"{i}. [{flag}] {c.name}\n   chat_id:{c.chat_id}")
    lines.append("\nUsa /chat_on <n> o /chat_off <n>")
    await update.message.reply_text("\n".join(lines))


async def _set_chat_enabled(update, context, enabled: bool) -> None:
    if await _deny_if_unauthorized(update):
        return
    verb = "chat_on" if enabled else "chat_off"
    arg = context.args[0] if context.args else None
    try:
        idx, chat = _resolve_telegram_chat(arg)
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(
            f"{exc}\n\nUso: /{verb} [n|nombre]\nEjemplo: /{verb} 1"
        )
        return

    if not chat.id:
        await update.message.reply_text("El chat no tiene id interno.")
        return

    if bool(chat.enabled) == bool(enabled):
        flag = "activo" if enabled else "desactivado"
        await update.message.reply_text(f"#{idx} {chat.name} ya estaba {flag}.")
        return

    try:
        updated = storage.update_telegram_chat(chat.id, TelegramChatUpdate(enabled=enabled))
    except (KeyError, ValueError) as exc:
        await update.message.reply_text(str(exc))
        return

    flag = "activo (recibe alertas)" if updated.enabled else "desactivado (no recibe alertas)"
    await update.message.reply_text(f"#{idx} {updated.name} → {flag}")


async def cmd_chat_on(update, context) -> None:
    await _set_chat_enabled(update, context, True)


async def cmd_chat_off(update, context) -> None:
    await _set_chat_enabled(update, context, False)


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
    app.add_handler(CommandHandler("chats", cmd_chats))
    app.add_handler(CommandHandler("chat_on", cmd_chat_on))
    app.add_handler(CommandHandler("chat_off", cmd_chat_off))
    return app


async def start_telegram_bot() -> None:
    """Start long-polling bot (call from FastAPI lifespan)."""
    global _application

    if not (settings.telegram_bot_token or "").strip():
        logger.info("Telegram bot disabled (no TELEGRAM_BOT_TOKEN)")
        return
    if not (settings.telegram_chat_id or "").strip():
        # Commands still work for chats saved in telegram_chats.json
        logger.warning(
            "TELEGRAM_CHAT_ID missing — only chats saved in Alerts UI can run commands"
        )

    app = _build_application()
    if app is None:
        return

    await app.initialize()
    await app.start()
    try:
        from telegram import BotCommand

        await app.bot.set_my_commands(
            [BotCommand(command=c, description=d) for c, d in BOT_COMMANDS]
        )
    except Exception:
        logger.exception("Could not register Telegram bot commands menu")
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
