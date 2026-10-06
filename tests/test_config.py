import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_invalid_database_url_does_not_leak_credentials() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            database_url="postgresql+asyncpg://user:ab#cr3t@db:5432/prismafi",
            redis_url="redis://localhost:6379/0",
        )

    assert "cr3t" not in str(exc_info.value)
