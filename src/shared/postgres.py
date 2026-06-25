from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from src.shared.settings import get_settings

_pool: asyncpg.Pool | None = None  # type: ignore[type-arg]
_pool_loop: asyncio.AbstractEventLoop | None = None


async def get_pool() -> asyncpg.Pool:  # type: ignore[type-arg]
    """Return a connection pool bound to the *current* event loop.

    Each Lambda invocation runs a fresh loop via ``asyncio.run()``. asyncpg
    pools (and their connections' futures) are bound to the loop they were
    created on, so a pool cached across invocations points at a closed loop and
    blows up with ``got Future <...> attached to a different loop`` /
    ``another operation is in progress``. We therefore key the cached pool by
    its loop and rebuild it whenever the loop changes.

    When the loop changed we ``terminate()`` (synchronous, force-closes the
    sockets) the stale pool first, so Supabase reclaims the session-mode slots
    instead of leaking them until idle timeout — which is what exhausted the
    pooler with ``EMAXCONNSESSION: max clients reached in session mode``.
    """
    global _pool, _pool_loop
    loop = asyncio.get_running_loop()
    if _pool is not None and _pool_loop is loop:
        return _pool
    if _pool is not None:
        _pool.terminate()
        _pool = None
        _pool_loop = None
    settings = get_settings()
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    _pool_loop = loop
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[Any, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
