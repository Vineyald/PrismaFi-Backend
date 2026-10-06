from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app
from app.modules.users.models import User
from tests.conftest import run_db

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
PASSWORD = "correct horse battery"


@pytest.fixture
def client(db: None) -> Iterator[TestClient]:
    # The context manager runs the lifespan, which disposes the engine's pool on exit.
    with TestClient(app) as client:
        yield client


def register(client: TestClient, **overrides: str) -> Any:
    body = {"name": "Ana Souza", "email": "ana@example.com", "password": PASSWORD, **overrides}
    return client.post(REGISTER, json=body)


def stored_users() -> list[User]:
    async def query(session: AsyncSession) -> list[User]:
        return list(await session.scalars(select(User)))

    return run_db(query)


def test_register_stores_normalized_email_and_argon2id_hash(client: TestClient) -> None:
    response = register(client, email="  Ana@Example.COM ", name="  Ana Souza ")

    assert response.status_code == 202
    assert response.content == b""
    [user] = stored_users()
    assert user.email == "ana@example.com"
    assert user.name == "Ana Souza"
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_register_with_taken_email_is_indistinguishable_and_keeps_the_account(
    client: TestClient,
) -> None:
    first = register(client)
    second = register(client, email="ANA@example.com", password="another password 123")

    assert (second.status_code, second.content) == (first.status_code, first.content)
    assert len(stored_users()) == 1
    assert client.post(LOGIN, json={"email": "ana@example.com", "password": PASSWORD}).is_success
    rejected = client.post(
        LOGIN, json={"email": "ana@example.com", "password": "another password 123"}
    )
    assert rejected.status_code == 401


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("password", "short"),
        ("password", "x" * 129),
        ("name", "   "),
        ("name", "Ana\x00Souza"),
    ],
)
def test_register_rejects_invalid_input(client: TestClient, field: str, value: str) -> None:
    response = register(client, **{field: value})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert stored_users() == []


def test_login_returns_short_lived_token_for_the_user(client: TestClient) -> None:
    register(client)

    response = client.post(LOGIN, json={"email": " ANA@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    claims = jwt.decode(
        body["access_token"], settings.jwt_secret.get_secret_value(), algorithms=["HS256"]
    )
    [user] = stored_users()
    assert claims["sub"] == str(user.id)
    assert timedelta(seconds=claims["exp"] - claims["iat"]) == timedelta(minutes=15)


def test_login_failures_do_not_reveal_whether_the_email_exists(client: TestClient) -> None:
    register(client)

    wrong_password = client.post(LOGIN, json={"email": "ana@example.com", "password": "nope"})
    unknown_email = client.post(LOGIN, json={"email": "bob@example.com", "password": "nope"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Invalid email or password"}


def test_login_with_unknown_email_still_verifies_a_hash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Skipping the Argon2 check for unknown emails would make them measurably faster.
    calls: list[str] = []
    verify = PasswordHasher.verify

    def spy(self: PasswordHasher, hash: str, password: str) -> bool:
        calls.append(hash)
        return verify(self, hash, password)

    monkeypatch.setattr(PasswordHasher, "verify", spy)

    response = client.post(LOGIN, json={"email": "nobody@example.com", "password": PASSWORD})

    assert response.status_code == 401
    assert len(calls) == 1


def test_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    secret = "my secret password " * 10  # over the 128-character limit

    response = client.post(LOGIN, json={"email": "ana@example.com", "password": secret})

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "my secret password" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "password"]


@pytest.mark.parametrize("email", ["not-an-email", "nobody@example.invalid"])
def test_login_answers_any_unusable_email_with_the_same_401(client: TestClient, email: str) -> None:
    response = client.post(LOGIN, json={"email": email, "password": PASSWORD})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_passwords_match_across_unicode_normalization_forms(client: TestClient) -> None:
    decomposed = "minha senha cafe\u0301 forte"  # e + combining acute accent
    composed = "minha senha caf\u00e9 forte"
    register(client, password=decomposed)

    response = client.post(LOGIN, json={"email": "ana@example.com", "password": composed})

    assert response.status_code == 200
