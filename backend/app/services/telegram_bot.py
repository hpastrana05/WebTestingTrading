import logging

from app.config import settings

logger = logging.getLogger(__name__)


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
        from telegram import Bot

        bot = Bot(token=token)
        message = await bot.send_message(chat_id=chat_id, text=text)
        return {"ok": True, "message_id": message.message_id}
    except Exception as exc:
        logger.exception("Telegram send failed")
        return {"ok": False, "detail": str(exc)}


def format_signal_alert(
    symbol: str,
    strategy_id: str,
    side: str,
    price: float,
    extra: str = "",
) -> str:
    lines = [
        f"Trading alert: {side.upper()}",
        f"Symbol: {symbol}",
        f"Strategy: {strategy_id}",
        f"Price: {price:.4f}",
    ]
    if extra:
        lines.append(extra)
    return "\n".join(lines)
