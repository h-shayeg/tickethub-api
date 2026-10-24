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
