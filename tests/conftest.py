"""Shared test setup.

The tests run against a real PostgreSQL database, because the most important
guarantees of this project (row locks, CHECK constraints, conditional UPDATEs)
only exist in PostgreSQL.

The test database is separate from the development database. Its URL comes
from TEST_DATABASE_URL, or else from DATABASE_URL with "_test" added to the
database name. It is dropped and rebuilt with Alembic at the start of every
run, and every table is emptied after every test.
"""

import os

from sqlalchemy.engine import make_url


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        base = os.environ.get("DATABASE_URL")
        if not base:
            raise RuntimeError("Set TEST_DATABASE_URL or DATABASE_URL to run the tests")
        url = make_url(base)
        url = url.set(database=f"{url.database}_test")
    if not url.database.endswith("_test"):
        # Every test run drops this database. Refuse anything that does not
        # look like a test database, so a typo can never wipe real data.
        raise RuntimeError(f"Test database name must end with '_test', got '{url.database}'")
    return url.render_as_string(hide_password=False)


# These must be set before anything from `app` is imported, because the
# settings object reads the environment once, at import time.
TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")

from collections.abc import Callable, Generator, Iterator  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.user import create_user  # noqa: E402
from tests.helpers import auth_headers, future  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TABLES = ("bookings", "events", "users")


def _recreate_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin_engine = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    """Build the schema once per run with the real migrations."""
    engine.dispose()
    _recreate_test_database()
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    counter = iter(range(1, 1_000_000))

    def _make_user(
        email: str | None = None,
        password: str = "correct-horse-battery",
        role: str = "user",
    ) -> User:
        user = create_user(db, email or f"user{next(counter)}@example.com", password)
        if role != "user":
            user.role = role
            db.commit()
            db.refresh(user)
        return user

    return _make_user


@pytest.fixture
def user_headers(make_user) -> dict[str, str]:
    return auth_headers(make_user())


@pytest.fixture
def admin_headers(make_user) -> dict[str, str]:
    return auth_headers(make_user(role="admin"))


@pytest.fixture
def make_event(db: Session) -> Callable[..., Event]:
    """Insert an event directly, so tests can also create events in the past."""

    def _make_event(
        title: str = "Concert",
        starts_at: datetime | None = None,
        price: int = 1000,
        total_tickets: int = 10,
        available_tickets: int | None = None,
        description: str | None = None,
    ) -> Event:
        event = Event(
            title=title,
            description=description,
            starts_at=starts_at or future(),
            price=price,
            total_tickets=total_tickets,
            available_tickets=(
                total_tickets if available_tickets is None else available_tickets
            ),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    return _make_event
