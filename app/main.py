import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import health
from app.core.config import settings
from app.core.database import engine
from app.core.redis import redis

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()
    await redis.aclose()


docs_enabled = settings.environment == "development"

# Everything lives under /api so the frontend can reach it through one same-origin
# path (Angular dev proxy now, a reverse proxy later). Business routes go under
# /api/v1; health and docs stay unversioned.
app = FastAPI(
    title="PrismaFi API",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url="/api/openapi.json" if docs_enabled else None,
    docs_url="/api/docs" if docs_enabled else None,
    redoc_url="/api/redoc" if docs_enabled else None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
    # Same JSON shape as HTTPException errors, no internals. Starlette re-raises after this,
    # so uvicorn logs the traceback once; logging it here too would duplicate it.
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router, prefix="/api")
