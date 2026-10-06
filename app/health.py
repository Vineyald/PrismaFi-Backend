import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2

CheckStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    service: str
    checks: dict[str, CheckStatus]


async def ping_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def ping_redis() -> None:
    await redis.ping()


async def _check(name: str, ping: Callable[[], Awaitable[None]]) -> CheckStatus:
    try:
        await asyncio.wait_for(ping(), timeout=CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        # Exception type only: driver messages can echo connection details.
        logger.warning("Health check %s failed: %s", name, type(exc).__name__)
        return "unavailable"
    return "ok"


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(response: Response) -> HealthResponse:
    """Readiness of the API and its dependencies. 503 when any dependency is down."""
    database, cache = await asyncio.gather(
        _check("database", ping_database), _check("redis", ping_redis)
    )
    checks: dict[str, CheckStatus] = {"database": database, "redis": cache}
    healthy = all(result == "ok" for result in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="healthy" if healthy else "unhealthy",
        service="prismafi-backend",
        checks=checks,
    )
