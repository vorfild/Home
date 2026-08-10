from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from sqlalchemy import text, update

from app.core.config import get_settings
from app.db.session import SessionFactory, engine
from app.models.identity import Session
from app.services.auth import now_utc
from app.services.backups import (
    ArchiveError,
    archive_database,
    create_archive,
    finalize_file_swap,
    restore_database,
    restore_physical_database,
    rollback_file_swap,
    stage_files,
    swap_files,
)


async def create(kind: str) -> None:
    async with SessionFactory.begin() as db:
        household_id = await db.scalar(text("SELECT id FROM households LIMIT 1"))
        if not household_id:
            raise ArchiveError("Семья ещё не создана")
        item = await create_archive(
            db,
            household_id=str(household_id),
            created_by_id=None,
            kind=kind,  # type: ignore[arg-type]
        )
        path = get_settings().backups_dir / item.path
    print(path, flush=True)


async def restore(path: Path) -> None:
    settings = get_settings()
    _, database = archive_database(path)
    stage = stage_files(path, settings.files_dir)
    previous: Path | None = None
    swapped = False
    try:
        await engine.dispose()
        physical = await restore_physical_database(path)
        if not physical:
            async with SessionFactory() as db:
                await restore_database(db, database)
                await db.commit()
        previous = swap_files(stage, settings.files_dir)
        swapped = True
        async with SessionFactory.begin() as db:
            await db.execute(update(Session).values(revoked_at=now_utc()))
        finalize_file_swap(previous)
    except Exception:
        if swapped:
            rollback_file_swap(previous, settings.files_dir)
        else:
            shutil.rmtree(stage, ignore_errors=True)
        raise
    print("restore-completed-sessions-revoked", flush=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or restore a verified Domovoy archive")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--kind", choices=("monthly", "manual", "insurance"), required=True)
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--archive", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = arguments()
    try:
        if args.command == "create":
            asyncio.run(create(args.kind))
        else:
            asyncio.run(restore(args.archive))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
