from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.core.config import get_settings


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("Missing required environment variable: DATABASE_URL")
        ssl_config: ssl.SSLContext | bool
        ssl_config = False if "localhost" in settings.database_url else ssl.create_default_context()
        _pool = await asyncpg.create_pool(dsn=settings.database_url, ssl=ssl_config)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection

