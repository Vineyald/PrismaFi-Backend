import asyncio
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import NullPool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Settings load at import time. Force them so a local .env cannot change test results.
# Database-backed tests use TEST_DATABASE_URL (a throwaway database, migrated and truncated by
# the `db` fixture); without it they are skipped. Other tests never open a real connection
# (engine and Redis connect lazily), so a placeholder URL suffices.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

os.environ["ENVIRONMENT"] = "development"
os.environ["CORS_ORIGINS"] = "[]"
os.environ["DATABASE_URL"] = (
    TEST_DATABASE_URL or "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"


@pytest.fixture(scope="session")
def migrated_database() -> None:
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    # A subprocess keeps Alembic's logging setup out of the test process.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def run_db[T](query: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `query` in its own transaction, outside the app.

    NullPool: asyncpg connections are bound to an event loop, and the app under TestClient
    runs on a different one, so the tests never share the app's pooled connections.
    """

    async def run() -> T:
        engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
                return await query(session)
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def db(migrated_database: None) -> None:
    """An empty, migrated database for one test."""

    async def truncate(session: AsyncSession) -> None:
        await session.execute(text("TRUNCATE users"))

    run_db(truncate)
