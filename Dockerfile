# Development image. Production images are a separate, later task.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

RUN useradd --create-home --uid 1000 app

# Install dependencies, including dev tools (alembic revision hooks run ruff), in their own
# layer so code edits do not reinstall them. The project itself is not installed:
# uvicorn, alembic and dramatiq import `app` from /srv.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install ".[dev]" && pip uninstall -y prismafi-backend \
    && rm -rf app build *.egg-info

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
