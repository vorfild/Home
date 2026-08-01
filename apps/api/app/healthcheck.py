from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine


async def check() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
