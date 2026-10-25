
import asyncio
import logging

from .engine import INTERVAL_SECONDS, run_monitoring_cycle

logger = logging.getLogger(__name__)

_task = None


async def _monitoring_loop():
    while True:
        try:
            result = await run_monitoring_cycle()
            logger.info(
                "Automatic monitoring cycle finished: status=%s",
                result.get("status"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatic monitoring cycle failed")

        await asyncio.sleep(INTERVAL_SECONDS)


def start_monitoring():
    global _task

    if _task is None or _task.done():
        _task = asyncio.create_task(_monitoring_loop())


async def stop_monitoring():
    global _task

    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass

    _task = None


def monitoring_is_running():
    return _task is not None and not _task.done()
