import unicodedata
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, EmailStr, Field, StringConstraints

# NIST SP 800-63B: length over composition rules. The upper bound caps hashing cost.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 254


def _normalize_email(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _normalize_password(value: Any) -> Any:
    # NFKC: the same visible password ("é" composed or decomposed) hashes the same way on every
    # device. Changing this later would invalidate existing hashes.
    return unicodedata.normalize("NFKC", value) if isinstance(value, str) else value


Password = Annotated[str, BeforeValidator(_normalize_password)]


class RegisterRequest(BaseModel):
    # No control characters: PostgreSQL cannot store NUL, and none belong in a display name.
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$"
        ),
    ]
    email: Annotated[EmailStr, BeforeValidator(_normalize_email)]
    password: Annotated[
        Password, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    ]


class LoginRequest(BaseModel):
    # Plain string, not EmailStr: any email that cannot sign in gets the same 401, whatever its
    # format. Normalized like registration so lookups match.
    email: Annotated[
        str,
        BeforeValidator(_normalize_email),
        StringConstraints(min_length=1, max_length=EMAIL_MAX_LENGTH),
    ]
    # No minimum: login never reveals the password policy, only that credentials are invalid.
    password: Annotated[Password, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - token type, not a secret
    expires_in: int = Field(description="Access token lifetime in seconds.")


class ErrorResponse(BaseModel):
    detail: str
