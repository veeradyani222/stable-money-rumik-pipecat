from __future__ import annotations

import asyncio
import ssl
from pathlib import Path

import asyncpg

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("Missing required environment variable: DATABASE_URL")

    backend_root = Path(__file__).resolve().parents[1]
    sql_path = backend_root / "migrations" / "001_demo_users.sql"
    sql = sql_path.read_text(encoding="utf-8")
    ssl_config: ssl.SSLContext | bool
    ssl_config = False if "localhost" in settings.database_url else ssl.create_default_context()

    connection = await asyncpg.connect(dsn=settings.database_url, ssl=ssl_config)
    try:
        await connection.execute(sql)
    finally:
        await connection.close()

    print(f"Applied {sql_path.relative_to(backend_root)}")


if __name__ == "__main__":
    asyncio.run(main())
