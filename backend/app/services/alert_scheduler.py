"""Background loop that evaluates alert rules on a fixed interval."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _loop() -> None:
    from app.services.alerts import check_alert_rules

    interval = max(0, int(settings.alert_check_interval_seconds or 0))
    logger.info("Alert checker started (every %ss)", interval)

    # Small delay so startup (Telegram bot, etc.) settles first
    await asyncio.sleep(5)

    while True:
        try:
            results = await check_alert_rules()
            fired = [
                r
                for r in results
                if r.get("ok") and r.get("event") not in (None, "none", "insufficient_data", "already_sent")
            ]
            errors = [r for r in results if not r.get("ok")]
            if fired or errors:
                logger.info(
                    "Alert check: %s rule(s), %s sent, %s error(s)",
                    len(results),
                    len(fired),
                    len(errors),
                )
            else:
                logger.debug("Alert check: %s rule(s), no new signals", len(results))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alert check failed")

        interval = max(0, int(settings.alert_check_interval_seconds or 0))
        if interval <= 0:
            logger.info("Alert checker stopped (interval disabled)")
            return
        await asyncio.sleep(interval)


def start_alert_checker() -> None:
    global _task
    interval = int(settings.alert_check_interval_seconds or 0)
    if interval <= 0:
        logger.info("Alert checker disabled (ALERT_CHECK_INTERVAL_SECONDS=0)")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(), name="alert-checker")


async def stop_alert_checker() -> None:
    global _task
    task = _task
    _task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Alert checker stopped")
