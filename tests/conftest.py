import os

# Settings load at import time. Force them so a local .env cannot change test results.
# Tests never open real connections (engine and Redis connect lazily): placeholder URLs suffice.
os.environ["ENVIRONMENT"] = "development"
os.environ["CORS_ORIGINS"] = "[]"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
