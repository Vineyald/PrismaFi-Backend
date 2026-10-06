import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import health
from app.main import app


async def _ok() -> None:
    return None


async def _down() -> None:
    raise ConnectionError("connection refused")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_healthy_when_dependencies_respond(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "ping_database", _ok)
    monkeypatch.setattr(health, "ping_redis", _ok)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "prismafi-backend",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_health_returns_503_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "ping_database", _ok)
    monkeypatch.setattr(health, "ping_redis", _down)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["checks"] == {"database": "ok", "redis": "unavailable"}


def test_unhandled_errors_do_not_leak_internals() -> None:
    @app.get("/api/_test_boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/_test_boom")
    finally:
        app.router.routes.pop()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret" not in response.text


def test_docs_and_schema_are_hidden_in_production() -> None:
    # Settings are read at import, so check a fresh interpreter with ENVIRONMENT=production.
    script = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        "for path in ('/api/docs', '/api/redoc', '/api/openapi.json'):\n"
        "    assert client.get(path).status_code == 404, path\n"
    )
    env = {**os.environ, "ENVIRONMENT": "production"}

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
