from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from src.shared.settings import get_settings

_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]


async def get_pool() -> asyncpg.Pool:  # type: ignore[type-arg]
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    assert _pool is not None
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[Any, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
