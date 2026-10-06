from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    # Deterministic constraint names, so Alembic can alter and drop them later.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


engine = create_async_engine(
    settings.database_url.unicode_string(),
    pool_pre_ping=True,
    # Keep bound values (amounts, identifiers, tokens) out of exception text and logs.
    hide_parameters=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session and one transaction per request: commit on success, roll back on error."""
    async with SessionLocal() as session, session.begin():
        yield session


# scope="function" commits before the response is sent, so a failed commit becomes an error
# response instead of a success the client already received.
SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
