import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.users.models import User

ACCESS_TOKEN_TTL = timedelta(minutes=15)

# Argon2id with the RFC 9106 low-memory profile (argon2-cffi defaults): 64 MiB per hash.
_hasher = PasswordHasher()
# Verified when the email is unknown, so a login takes the same time whether or not the
# account exists.
_DUMMY_HASH = _hasher.hash("prismafi-dummy-password")
# Caps concurrent hashes so a burst of auth requests cannot exhaust memory or the default
# thread pool; extra requests wait their turn. Rate limiting (next deliverable) cuts the burst.
_hash_slots = asyncio.Semaphore(4)


class InvalidCredentialsError(Exception):
    pass


async def _hash(password: str) -> str:
    async with _hash_slots:
        return await asyncio.to_thread(_hasher.hash, password)


async def _verify(password_hash: str, password: str) -> bool:
    async with _hash_slots:
        try:
            return await asyncio.to_thread(_hasher.verify, password_hash, password)
        except VerifyMismatchError:
            return False


async def register(session: AsyncSession, data: RegisterRequest) -> None:
    """Create the account unless the email is taken. Both outcomes look the same to the caller.

    The hash is computed in both cases and the insert is a single statement, so neither the
    response nor its timing reveals whether the email was already registered. ON CONFLICT also
    makes two concurrent registrations of the same email safe. Hashing runs before the session
    touches the database, so no connection is held during it.
    """
    password_hash = await _hash(data.password)
    await session.execute(
        insert(User)
        .values(email=data.email, name=data.name, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[User.email])
    )


async def login(data: LoginRequest) -> str:
    """Return an access token, or raise InvalidCredentialsError for any bad email/password."""
    # Own short session: the connection returns to the pool before the slow hash check.
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == data.email))
    valid = await _verify(user.password_hash if user else _DUMMY_HASH, data.password)
    if user is None or not valid:
        raise InvalidCredentialsError
    return create_access_token(user.id)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
