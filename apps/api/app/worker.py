from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionFactory, engine
from app.models.identity import LoginAttempt, Session
from app.services.backups import create_monthly_if_due
from app.services.home import process_home_schedules
from app.services.lifecycle import purge_expired_trash, unlink_purged_files
from app.services.notifications import dispatch_notifications, generate_due_notifications
from app.services.storage import process_storage_timers

logger = logging.getLogger("domovoy.worker")


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def clean_identity_records() -> None:
    now = datetime.now(UTC)
    retention_cutoff = now - timedelta(days=7)
    attempts_cutoff = now - timedelta(days=1)
    async with SessionFactory.begin() as session:
        await session.execute(
            delete(Session).where(
                or_(
                    Session.expires_at < retention_cutoff,
                    Session.revoked_at < retention_cutoff,
                )
            )
        )
        await session.execute(
            delete(LoginAttempt).where(LoginAttempt.attempted_at < attempts_cutoff)
        )


async def process_domain_schedules() -> None:
    async with SessionFactory.begin() as session:
        await process_storage_timers(session)
        purge_result = await purge_expired_trash(session)
        await process_home_schedules(session)
        await generate_due_notifications(session)
        await dispatch_notifications(session)
        await create_monthly_if_due(session)
    await unlink_purged_files(purge_result.paths)


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
            await clean_identity_records()
            await process_domain_schedules()
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
