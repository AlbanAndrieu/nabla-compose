# FastAPI Sample - AI Agent Instructions

## Architecture Overview

This is a **production-grade FastAPI application** (`nabla/`) with comprehensive observability, multi-database support, and enterprise integrations:

- **Main entry**: `nabla/fastapi_server.py` - FastAPI app with DD tracing, Sentry, Prometheus, and Pyroscope profiling
- **API structure**: Modular routers in `nabla/api/` (ping, v1, v2, users, notes, demo)
- **Database**: PostgreSQL via SQLAlchemy + Alembic migrations, psycopg3 connection pooling (`nabla/api/db/database.py`)
- **Auth**: Keycloak integration with JWT (`nabla/api/auth/keycloak.py`, `nabla/api/users/`)
- **Config**: Pydantic Settings in `nabla/config_settings.py` with environment-based configuration
- **Integrations**: Temporal workflows (`nabla/temporalio/`), Redis caching, DefectDojo, Loki logging

## Development Workflow

### Package Management

- **Poetry** is primary (see extensive `[tool.poetry.group.*]` in `pyproject.toml`)
- Run `poetry install --all-extras` for full setup or specific groups: `--with api,temporal,test`
- **pipenv** also supported: `python -m pipenv install --dev`
- Python 3.12+ required (`pyenv install 3.12.3`)

### Build & Run Commands (Makefile-driven)

```bash
make up-uvicorn        # Development server (port 8091)
make up-gunicorn       # Production server with workers
make test              # Run all tests with pytest
make test-fastest      # Quick test run (fail-fast)
make test-continuous   # Watch mode with pytest-watcher
make lint              # Ruff linting
make format            # Ruff formatting
make build-docker      # Build container image
```

### Testing Conventions

- **Fixtures**: `tests/unit/conftest.py` provides `test_app` (TestClient), custom `requires_env()` decorator
- **Markers**: `@pytest.mark.webtest`, `@pytest.mark.skip(reason="...")`
- **Mocking**: Use `monkeypatch` fixture extensively (see `tests/unit/test_notes.py`)
- **Async**: Tests auto-detected with `asyncio_mode = auto` in `pytest.ini`
- **Acceptable failure rate**: 50% threshold configured in conftest (session hook)
- **Environment mocking**: Mock credentials defined in `pytest.ini` env section

### Code Quality Standards

- **Ruff** for formatting + linting: `ruff format .` then `ruff check . --fix`
- **Type checking**: Pyright configured via `pyrightconfig.json`
- **Pre-commit hooks**: Run `pre-commit install` (includes ruff, pyright, security checks)
- **Line length**: 88 chars (black-compatible)
- **Import order**: Ruff handles sorting automatically

## Key Patterns & Conventions

### Database Patterns

- **Dual engines**: `DB_URL` (async with psycopg) and `DB_URL_INIT` (sync for pytest/migrations)
- **Connection pooling**: Custom psycopg3 pool with `min_size=0, max_size=1` (see `nabla/api/db/database.py`)
- **JSON serialization**: Uses `orjson` for performance (`orjson_serializer()` function)
- **Session management**: `AsyncSessionLocal` for async routes, `SessionLocal` for sync operations
- **Alembic migrations**: `alembic/` directory, run `alembic upgrade head`

### API Response Patterns

- **ORJSONResponse** as default response class for performance
- **Status codes**: 201 for creation, explicit 404/400 handling
- **Rate limiting**: SlowAPI with `@limiter.limit()` decorators
- **Feature flags**: FastAPI-FeatureFlags integration with Unleash

### Observability Stack

- **Datadog**: Automatic tracing via `ddtrace` (patch applied in fastapi_server.py), profiler starts early
- **Metrics**: Prometheus `/metrics` endpoint with custom middleware (`nabla/utils/prometheus.py`)
- **Logging**: Structured logging via `structlog` + custom LogMiddleware
- **Tracing**: OpenTelemetry integration with DD agent on `datadog-agent.service.gra.uat.consul:4317`
- **Profiling**: Pyroscope (`PYROSCOPE_ENDPOINT=http://localhost:4040`)
- **Error tracking**: Sentry SDK with FastAPI integration

### Configuration Management

- **Multi-environment**: `.env.local`, `.env.secrets` loaded by docker-compose
- **Settings class**: `_Settings` in `config_settings.py` with Pydantic validation
- **Service discovery**: Consul-based URLs (e.g., `pg-gra.service.gra.dev.consul`)
- **Secrets**: SecretStr for sensitive values (Redis password, API keys)

### Docker & Deployment

- **Multi-stage build**: `Dockerfile` with `builder-base` target for caching
- **Secrets**: Build-time secrets for GitLab tokens (`--secret id=CI_JOB_TOKEN`)
- **Registry**: `registry.gitlab.com/jusmundi-group/proof-of-concept/fastapi-sample`
- **Image tag pattern**: `OCI_TAG` defaults to `1.1.3`, configurable via env var

## Common Pitfalls

1. **Database URL confusion**: Use `DB_URL_INIT` for sync operations (Alembic, pytest), `DB_URL` for async FastAPI routes
2. **psycopg version**: Uses psycopg3 (`psycopg[binary,pool]`), NOT psycopg2
3. **Environment variables**: Many services have mock values in `pytest.ini` but need real values for manual testing
4. **DD tracing**: `patch(sqlalchemy=True)` must occur before engine creation
5. **Async sessions**: Always use `async with AsyncSessionLocal()` pattern, never manual commit/close

## Project-Specific Commands

```bash
# Database setup (requires Consul-accessible PostgreSQL)
alembic upgrade head

# Local Jupyter setup (uses Miniconda)
make setup-jupyter-local
make jupyter-local

# Vite UI (separate Vue.js client)
cd vue-client/ && npm run dev

# Redis required for caching/websockets
sudo service redis-server start
redis-cli -c -h localhost -p 6379

# Health & metrics endpoints
curl http://localhost:8091/health
curl http://localhost:8091/metrics
curl http://localhost:8091/ping
```

## Repository Context

- **Primary language for API**: Python 3.12+ with extensive type hints
- **Alternative files**: Nomad job specs, Nix flakes for reproducible envs
- **CI/CD**: GitHub Actions in `.github/workflows/` (tests, linting, CodeQL, release)
- **Documentation**: Sphinx docs in `docs/`, serve with `make docs-serve`
- **Notebooks**: Training examples in `notebooks/` (Jupyter)

## When Editing

1. **New API routes**: Create in appropriate `nabla/api/` subdirectory, register router in `fastapi_server.py`
2. **Database models**: Add to relevant `models.py`, create Alembic migration with `alembic revision --autogenerate`
3. **Tests**: Add to `tests/unit/`, use existing fixtures from `conftest.py`
4. **Dependencies**: Update `[tool.poetry.group.GROUP]` in `pyproject.toml`, run `poetry lock`
5. **Format before commit**: `make format` then `make lint` to match CI expectations

---

## applyTo: "\*\*"

# Project general coding standards

## Naming Conventions

- Use PascalCase for component names, interfaces, and type aliases
- Use camelCase for variables, functions, and methods
- Prefix private class members with underscore (\_)
- Use ALL_CAPS for constants

## Error Handling

- Use try/catch blocks for async operations
- Implement proper error boundaries in Vue components
- Always log errors with contextual information
