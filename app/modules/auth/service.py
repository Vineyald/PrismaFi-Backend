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
from app.modules.auth.schemas import LoginRequest, RegisterRequest
from app.modules.users.models import User

ACCESS_TOKEN_TTL = timedelta(minutes=15)

# Argon2id with the RFC 9106 low-memory profile (argon2-cffi defaults).
_hasher = PasswordHasher()
# Verified when the email is unknown, so a login takes the same time whether or not the
# account exists.
_DUMMY_HASH = _hasher.hash("prismafi-dummy-password")


class InvalidCredentialsError(Exception):
    pass


async def register(session: AsyncSession, data: RegisterRequest) -> None:
    """Create the account unless the email is taken. Both outcomes look the same to the caller.

    The hash is computed in both cases and the insert is a single statement, so neither the
    response nor its timing reveals whether the email was already registered. ON CONFLICT also
    makes two concurrent registrations of the same email safe.
    """
    password_hash = await asyncio.to_thread(_hasher.hash, data.password)
    await session.execute(
        insert(User)
        .values(email=data.email, name=data.name, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[User.email])
    )


async def login(session: AsyncSession, data: LoginRequest) -> str:
    """Return an access token, or raise InvalidCredentialsError for any bad email/password."""
    user = await session.scalar(select(User).where(User.email == data.email))
    try:
        # Argon2 is CPU-bound: run it off the event loop.
        await asyncio.to_thread(
            _hasher.verify, user.password_hash if user else _DUMMY_HASH, data.password
        )
    except VerifyMismatchError:
        raise InvalidCredentialsError from None
    if user is None:
        raise InvalidCredentialsError
    return create_access_token(user.id)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": now, "exp": now + ACCESS_TOKEN_TTL}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
