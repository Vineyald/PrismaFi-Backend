# PrismaFi Backend

The PrismaFi API, a FastAPI **modular monolith**. PrismaFi will centralize financial accounts, bills, bank connections (Open Finance), transactions and payment initiation. This repository is currently the technical foundation only. It has configuration, PostgreSQL, Redis, a background-job broker and a health endpoint. It has no product features yet.

The frontend lives in a separate repository (`PrismaFi-Frontend`). The two repositories integrate only through HTTP and the OpenAPI schema published here.

## Technology Stack

| Technology | Why it is here |
|---|---|
| **Python 3.12+** (developed on 3.14) | Strong ecosystem for finance, data and integrations. `requires-python >= 3.12`. The Docker image uses 3.14. |
| **FastAPI** | Async HTTP framework. It generates the OpenAPI schema from typed code, and that schema is the frontend contract. |
| **Pydantic v2** / **pydantic-settings** | Request and response validation and serialization. Typed configuration from environment variables. |
| **SQLAlchemy 2** (async) + **asyncpg** | ORM and query layer with the async PostgreSQL driver. |
| **PostgreSQL** | Primary database. It has transactional integrity, `NUMERIC` for money, and constraints for idempotency. |
| **Alembic** | Versioned schema migrations. |
| **Redis** | Cache and message broker. |
| **Dramatiq** | Background jobs (provider sync, webhooks, notifications), using Redis as the broker. Chosen over Celery for its simpler model and smaller surface. |
| **httpx** | Used by FastAPI's `TestClient` today. It becomes the outbound HTTP client for provider integrations, and moves to runtime dependencies then. |
| **Uvicorn** | ASGI server. |
| **Pytest** | Tests. |
| **Ruff** | Linter and formatter. Rule set: pycodestyle, pyflakes, isort, pyupgrade, bugbear, async pitfalls, bandit security checks. |
| **mypy** (strict) | Static typing, with the Pydantic plugin. |
| **Docker / Docker Compose** | One-command local stack: API, worker, PostgreSQL, Redis. |

## Architecture

Modular monolith. It uses clean boundaries without ceremony: a layer is added only when it removes a real problem.

```text
PrismaFi-Backend/
├── app/
│   ├── core/              # Infrastructure shared by every module
│   │   ├── config.py      # Settings (env vars / .env), validated at startup
│   │   ├── database.py    # Async engine + declarative Base with constraint naming convention
│   │   ├── redis.py       # Shared async Redis client
│   │   └── broker.py      # Dramatiq Redis broker
│   ├── health.py          # GET /api/health (readiness: DB + Redis)
│   └── main.py            # App assembly: routers, CORS, error handler, lifespan
├── migrations/
│   ├── env.py             # Alembic env: uses app settings and Base.metadata
│   ├── script.py.mako     # Revision template
│   └── versions/          # Revisions (none yet)
├── tests/
│   ├── conftest.py        # Forces test settings, independent of your .env
│   └── test_health.py
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

**Responsibilities**

- `app/core/` holds infrastructure only. It never imports from business modules.
- `app/main.py` wires everything together. It is the only place that knows about every router.
- Business domains (`auth`, `accounts`, `transactions`, `payments`, …) will live in `app/modules/<name>/`. Each module owns its `router.py`, `schemas.py` (Pydantic), `models.py` (SQLAlchemy) and `service.py` (business rules). It adds a `tasks.py` for Dramatiq actors only when needed. Routes stay thin and business logic lives in the service. A repository layer is added only if it removes real duplication or complexity.
- **None of these folders exist yet, on purpose.** Empty architecture for hypothetical code is not created. `app/modules/` appears with the first real domain.

**API layout**

Everything is served under `/api`, so the frontend reaches the API through a single same-origin path: the Angular dev proxy now, a reverse proxy in production.

| Path | Purpose |
|---|---|
| `/api/health` | Unversioned health check, for infrastructure probes |
| `/api/v1/...` | Business endpoints (versioned) — none yet |
| `/api/docs`, `/api/redoc`, `/api/openapi.json` | API documentation (development only) |

## Setup

Prerequisites: Python 3.12+, Docker Desktop (which requires WSL 2 on Windows), Git.

```bash
# 1. Clone
git clone <repo-url> PrismaFi-Backend
cd PrismaFi-Backend

# 2. Environment
cp .env.example .env            # edit values if needed

# 3. Python dependencies (for tests, lint, IDE, host-run commands)
python -m venv .venv            # Windows: py -3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 4. Run the full stack: PostgreSQL, Redis, API (hot reload), worker.
#    The api service runs `alembic upgrade head` before starting.
docker compose up --build

# 5. Check it
curl http://localhost:8000/api/health
```

The API is then at http://localhost:8000, with docs at http://localhost:8000/api/docs.

**Running the API on the host instead of in Docker**, which is useful for debuggers:

```bash
docker compose up -d db redis
alembic upgrade head
uvicorn app.main:app --reload
```

**Tests and quality**

```bash
pytest
ruff check .
ruff format --check .
mypy app migrations tests
```

## Environment Variables

All are defined in `.env.example`. Settings are validated at startup: a missing or invalid required value stops the app.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ENVIRONMENT` | no | `production` | `development` or `production`. Production disables `/api/docs`, `/api/redoc` and `/api/openapi.json`. The default fails closed: a deploy that forgets it gets production behavior. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `POSTGRES_USER` | compose | — | Database user created by the Postgres container. Also used to build the container `DATABASE_URL`. |
| `POSTGRES_PASSWORD` | compose | — | Its password. Keep it URL-safe (letters, digits, `- _ .`), because it is embedded in a URL without encoding. |
| `POSTGRES_DB` | compose | — | Database name. |
| `DATABASE_URL` | **yes** | — | `postgresql+asyncpg://user:pass@host:5432/db`. In `.env` it points at `localhost`, for host-run commands, and must match the `POSTGRES_*` values. Compose overrides the host to `db` inside containers. |
| `REDIS_URL` | **yes** | — | `redis://host:6379/0`. Compose overrides the host to `redis`. |
| `CORS_ORIGINS` | no | `[]` | JSON list of browser origins allowed cross-origin, e.g. `["https://app.example.com"]`. Empty disables CORS, which is correct while the frontend is same-origin. |

Empty values (`VAR=`) fall back to the default. Real secrets never go in the repo: `.env`, `.env.*`, `*.pem`, `*.key` and `*.p12` are git- and docker-ignored.

## Database

- **PostgreSQL 18** runs in Docker Compose, with data in the `postgres-data` volume. It is published on `127.0.0.1:5432` only.
- **SQLAlchemy 2 async**: `app/core/database.py` provides the `engine` and the declarative `Base`.
  - `Base.metadata` has a **naming convention** for indexes and constraints, so Alembic can alter and drop them reliably.
  - The engine uses `hide_parameters=True`, so bound values (amounts, identifiers, tokens) never appear in exception text or logs.
  - The session factory and `get_session` dependency are added here together with the first model. Nothing needs them yet.
- **Alembic** reads the URL from app settings. `alembic.ini` contains no credentials.

**Migration workflow**

```bash
# 1. Add/modify models in app/modules/<name>/models.py
# 2. Import the models module in migrations/env.py (so autogenerate sees it)
alembic revision --autogenerate -m "create accounts table"
# 3. Review the generated file in migrations/versions/. Autogenerate is a draft, not truth.
alembic upgrade head
alembic downgrade -1          # every migration must be reversible
alembic upgrade head --sql    # print SQL without a database (review / production)
```

New revisions are passed through `ruff check --fix` and `ruff format` automatically (`post_write_hooks` in `alembic.ini`).

## Background Jobs

- `app/core/broker.py` creates the Dramatiq `RedisBroker` from `REDIS_URL` and registers it globally.
- The `worker` service in Compose runs `dramatiq app.core.broker --processes 1 --threads 2`.
- **No actors exist yet.** The worker starts and connects to Redis, ready for the first real job. No fake jobs were created.

Adding a job:

```python
# app/modules/<name>/tasks.py
import dramatiq
from app.core.broker import broker


@dramatiq.actor(broker=broker, max_retries=5)
def sync_connection(connection_id: str) -> None: ...
```

Then add the module to the worker command: `dramatiq app.core.broker app.modules.<name>.tasks`. Jobs must be **idempotent**, because Dramatiq retries on failure.

## API

| URL | What |
|---|---|
| http://localhost:8000/api/docs | Swagger UI (development only) |
| http://localhost:8000/api/redoc | ReDoc (development only) |
| http://localhost:8000/api/openapi.json | OpenAPI 3.1 schema (development only). The frontend generates its TypeScript types from this. |
| `GET /api/health` | Readiness |

`GET /api/health` checks PostgreSQL (`SELECT 1`) and Redis (`PING`) concurrently, with a 2s timeout each:

```json
// 200 OK
{ "status": "healthy", "service": "prismafi-backend", "checks": { "database": "ok", "redis": "ok" } }
// 503 Service Unavailable
{ "status": "unhealthy", "service": "prismafi-backend", "checks": { "database": "unavailable", "redis": "ok" } }
```

Failures are logged by exception type only, because driver messages can echo connection details. Unhandled errors return `500 {"detail": "Internal server error"}` and never expose internals. The traceback goes to the server log.

## Quality

| Tool | Command | Config |
|---|---|---|
| Ruff (lint) | `ruff check .` | `[tool.ruff]` in `pyproject.toml` |
| Ruff (format) | `ruff format .` | same |
| mypy | `mypy app migrations tests` | `strict = true` + Pydantic plugin |
| Pytest | `pytest` | `tests/` |

The current tests cover:
- the health endpoint in both healthy and dependency-down states, with the dependency pings stubbed;
- the generic 500 response, which must not leak internals;
- docs and schema being hidden when `ENVIRONMENT=production`.

## Docker

`docker compose up --build` starts:

| Service | Image | Notes |
|---|---|---|
| `api` | built from `Dockerfile` | Runs `alembic upgrade head`, then `uvicorn --reload`. `./app` and `./migrations` are bind-mounted, so edits reload live (polling is enabled because Windows bind mounts do not deliver file events). Port `127.0.0.1:8000`. |
| `worker` | same image | The Dramatiq worker. |
| `db` | `postgres:18-alpine` | TCP health check. Port `127.0.0.1:5432`. |
| `redis` | `redis:8-alpine` | Health check `redis-cli ping`. Port `127.0.0.1:6379`. |

`api` and `worker` wait for healthy `db` and `redis` and restart on failure. The image is development-oriented: it runs as non-root uid 1000, and it installs dependencies, including dev tools (ruff, used by the migration hooks), in a cached layer. Production images and deployment are a separate task. No Nginx is included.

Useful commands: `docker compose logs -f api`, `docker compose exec api alembic revision --autogenerate -m "..."`, and `docker compose down -v`. The last one **deletes the database volume**.

## Financial Development Rules

These are mandatory for all future code.

1. **Never use binary floating point for money.** Use `Decimal` in Python, `NUMERIC(p, s)` in PostgreSQL, and string-encoded decimals in JSON. Every amount carries its currency, and rounding is explicit (`quantize` with a named rounding mode).
2. **Payment operations are idempotent.** Clients send an idempotency key, and a database unique constraint enforces it. Code assumes retries, double-clicks, and failures after successful processing.
3. **Webhooks may arrive duplicated, late or out of order.** Verify signatures, deduplicate by event ID, and only allow valid state transitions.
4. **Provider calls can time out after succeeding.** Reconcile; never blindly retry money movement.
5. **Never log** passwords, tokens, bank credentials or full financial payloads. `hide_parameters=True` covers SQL; application code must do the same.
6. **Timestamps are timezone-aware and stored in UTC.**
7. **No custom cryptography, and never store bank credentials.**

## Known limitations

- Dependencies use version floors (`>=`) with no lock file yet, so builds are not fully reproducible. Add a lock (e.g. `uv lock` or `pip-compile --generate-hashes`) before CI and production.
- `/api/health` is unauthenticated and touches the DB and Redis. Before a public deploy, rate-limit it at the reverse proxy, or split it into a public liveness check and an internal readiness check.
