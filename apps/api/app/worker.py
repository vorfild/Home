from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger("domovoy.worker")


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def run_worker() -> None:
    settings = get_settings()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop_event.set)

    logger.info("worker_started", extra={"poll_interval": settings.worker_poll_interval_seconds})
    while not stop_event.is_set():
        try:
            await check_database()
            logger.debug("worker_heartbeat")
        except Exception:
            logger.exception("worker_database_check_failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.worker_poll_interval_seconds)
        except TimeoutError:
            continue

    await engine.dispose()
    logger.info("worker_stopped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Domovoy background worker")
    parser.add_argument("--healthcheck", action="store_true")
    return parser.parse_args()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = parse_args()
    if args.healthcheck:
        asyncio.run(check_database())
        return
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
