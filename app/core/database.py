from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import create_async_engine
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
