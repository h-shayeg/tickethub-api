# TicketHub API

[![CI](https://github.com/h-shayeg/tickethub-api/actions/workflows/ci.yml/badge.svg)](https://github.com/h-shayeg/tickethub-api/actions/workflows/ci.yml)

A REST API for booking event tickets, built with FastAPI and PostgreSQL.
Admins publish events, users book and cancel tickets, and the API guarantees
that an event is never oversold, even when many people buy at the same moment.

## Highlights

- **No overselling under concurrency.** Checking stock and taking tickets happen
  in one conditional `UPDATE`, so PostgreSQL's row lock decides who gets the
  last ticket. An automated test sends 12 simultaneous requests for 5 tickets
  and expects exactly 5 bookings. The same test fails against a naive
  read-then-write version.
- **Rules enforced by the database, not only by Python.** CHECK constraints and
  foreign keys keep stock, prices, statuses and roles valid even if application
  code has a bug.
- **Careful authentication.** Argon2 password hashes, short-lived JWTs with
  strict validation, the same answer for a wrong email and a wrong password,
  and roles read from the database on every request.
- **101 automated tests against a real PostgreSQL database,** run with every
  migration check and Docker build on GitHub Actions.
- **Every design choice is written down** in [docs/DECISIONS.md](docs/DECISIONS.md),
  including the trade-offs and known limitations.

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 · Alembic · Pydantic 2 ·
PyJWT · Argon2 (pwdlib) · pytest · Docker Compose · GitHub Actions

## Quick start

You need Docker with Docker Compose.

```bash
git clone https://github.com/h-shayeg/tickethub-api.git
cd tickethub-api
cp .env.example .env
```

Open `.env` and replace `SECRET_KEY` with a long random string. One way to
make one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the API and the database, then create the tables:

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
```

The interactive documentation is now at <http://localhost:8000/docs>.

### Create the first admin

Register a user (in `/docs`, or with the `curl` example below), then promote it:

```bash
docker compose exec api python -m app.cli make-admin you@example.com
```

`remove-admin` takes the role away. There is deliberately no HTTP endpoint for
this.

### Try it with curl

```bash
# Register, make yourself admin, and log in ("username" in the login form is the email)
curl -X POST localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "a-long-password"}'

docker compose exec api python -m app.cli make-admin you@example.com

curl -X POST localhost:8000/api/v1/auth/login \
  -d "username=you@example.com&password=a-long-password"
# Copy access_token from the answer:
TOKEN=paste-the-token-here

# Create an event (admin only; prices are in the smallest currency unit)
curl -X POST localhost:8000/api/v1/events \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title": "Jazz Night", "starts_at": "2030-05-01T19:30:00Z", "price": 2500, "total_tickets": 100}'

# Book 2 tickets, list your bookings, cancel one
curl -X POST localhost:8000/api/v1/bookings \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"event_id": 1, "quantity": 2}'

curl localhost:8000/api/v1/bookings -H "Authorization: Bearer $TOKEN"

curl -X POST localhost:8000/api/v1/bookings/1/cancel -H "Authorization: Bearer $TOKEN"
```

## Running the tests

```bash
docker compose exec api pytest
```

The tests use their own database (`tickethub_test`), which is dropped and
rebuilt from the migrations on every run. Your development data is never
touched. To run them without Docker, set `DATABASE_URL` (or
`TEST_DATABASE_URL`) to a PostgreSQL server you can create databases on, then:

```bash
pip install -r requirements-dev.txt
pytest
```

## API

All routes live under `/api/v1`.

| Method | Path | Who | What it does |
| --- | --- | --- | --- |
| GET | `/health` | anyone | The API process is up |
| GET | `/health/db` | anyone | The database answers (503 if not) |
| POST | `/auth/register` | anyone | Create an account (always role `user`) |
| POST | `/auth/login` | anyone | Get a 30-minute access token |
| GET | `/users/me` | user | The current user |
| GET | `/events` | anyone | List events: `limit`, `offset`, `q`, `upcoming`, `available_only` |
| GET | `/events/{id}` | anyone | One event |
| POST | `/events` | admin | Create an event |
| PATCH | `/events/{id}` | admin | Change title, description, time or price |
| DELETE | `/events/{id}` | admin | Delete an event that has no bookings |
| POST | `/bookings` | user | Book 1 to 10 tickets for an upcoming event |
| GET | `/bookings` | user | Your own bookings, newest first |
| POST | `/bookings/{id}/cancel` | user | Cancel your booking before the event starts |

Errors use clear status codes: `401` no or bad token, `403` not an admin,
`404` not found, `409` a business rule said no (sold out, already started,
already cancelled, email taken, event has bookings), `422` invalid input.

## Project structure

```
app/
  api/v1/      HTTP layer: routes, status codes, permissions
  api/deps.py  Shared dependencies: database session, current user, admin check
  services/    Business logic, knows nothing about HTTP
  models/      SQLAlchemy tables and database rules
  schemas/     Pydantic request and response shapes
  core/        Settings, database engine, password hashing and tokens
  cli.py       Admin commands (make-admin, remove-admin)
alembic/       Database migrations
tests/         pytest suite, run against real PostgreSQL
docs/          Design decisions
```

## Known limitations

These are conscious choices for the current size of the project. Each one is
explained in [docs/DECISIONS.md](docs/DECISIONS.md).

- No idempotency key: a double click creates two bookings (the user can cancel one).
- No refresh tokens or token revocation: an access token lives until it expires.
- Offset pagination: rows added between two page requests can shift the pages.
- No payments, ticket tiers or seat maps yet.
