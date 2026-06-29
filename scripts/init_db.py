#!/usr/bin/env python3
"""Initialize the production database schema (idempotent).

Creates any missing tables from the SQLAlchemy models against ``DATABASE_URL``.
Run on container startup (see ``start.sh``) so a fresh database is immediately
usable. Safe to run repeatedly: ``create_all`` only creates tables that do not
already exist and never drops or alters existing ones.

History: the container previously *skipped* DB migrations (alembic had a
duplicate-column issue), which left a fresh ``trading_db`` with no tables at all,
so every account/portfolio/order query failed with
``UndefinedTableError: relation "accounts" does not exist``. This replaces that
skip with a direct, idempotent schema creation.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.database.trading  # noqa: F401  (registers models on Base.metadata)
from app.models.database.base import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://trading_user:trading_password@localhost:5432/trading_db",
)


async def init_database() -> None:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            count = result.scalar()
        target = DATABASE_URL.rsplit("@", 1)[-1]
        print(f"✅ Database schema ready ({count} tables) at {target}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
