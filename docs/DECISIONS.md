# Design Decisions

## Step 1: Project skeleton

- **Configuration via environment variables.** Secrets and settings live in `.env`
  (never committed). `.env.example` documents the variables the project needs.
- **API versioning from day one.** All routes live under `/api/v1`, so a future
  breaking change can ship as `/api/v2` without breaking existing clients.
- **Layered structure.** `api/` handles HTTP and `core/` holds configuration.
  Business logic will live in `services/` and database code in `models/`, so each
  part stays small and easy to test.
- **Docker Compose for local development.** One command starts the API and
  PostgreSQL. The database has a healthcheck, so the API only starts once
  Postgres accepts connections.
- **Pinned dependency versions.** Everyone gets the same versions, so builds are
  reproducible.
- **Configurable pip index.** The Dockerfile takes a `PIP_INDEX_URL` build
  argument that defaults to the official PyPI. Developers on restricted networks
  can override it in their local `.env` (never committed) without changing the
  Dockerfile or affecting CI.

## Step 2: Database connection

- **SQLAlchemy 2 with the psycopg 3 driver.** SQLAlchemy is the standard ORM in
  the Python ecosystem. The `[binary]` build of psycopg bundles libpq, so the
  Docker image needs no extra system packages.
- **No default value for `DATABASE_URL`.** If it is missing, the app refuses to
  start instead of silently connecting to the wrong database (fail fast).
- **One session per request.** `get_db` is a FastAPI dependency that opens a
  session and always closes it in a `finally` block, so connections are never
  leaked from the pool.
- **`pool_pre_ping=True`.** The pool checks a connection before using it, so the
  API recovers on its own after a database restart.
- **Separate health checks.** `/health` only says the API process is up.
  `/health/db` also queries the database and returns 503 (not a crash with 500)
  when it is down.
- **Verified manually.** With the database container stopped, `/health` stays
  200 and `/health/db` returns 503. After the database restarts, `/health/db`
  returns 200 again without restarting the API.
