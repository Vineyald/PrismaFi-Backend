from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, EmailStr, Field, StringConstraints

# NIST SP 800-63B: length over composition rules. The upper bound caps hashing cost.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


def _normalize_email(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


Email = Annotated[EmailStr, BeforeValidator(_normalize_email)]


class RegisterRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    email: Email
    password: Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


class LoginRequest(BaseModel):
    email: Email
    # No minimum: login never reveals the password policy, only that credentials are invalid.
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - token type, not a secret
    expires_in: int = Field(description="Access token lifetime in seconds.")


class ErrorResponse(BaseModel):
    detail: str
