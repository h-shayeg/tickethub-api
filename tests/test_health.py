from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.main import app


def test_health_is_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_db_is_ok_when_database_is_up(client):
    response = client.get("/api/v1/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_health_db_returns_503_when_database_is_down(client):
    # Port 1 has nothing listening, so every connection attempt fails.
    dead_engine = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nothing",
        connect_args={"connect_timeout": 2},
    )
    DeadSession = sessionmaker(bind=dead_engine)

    def get_dead_db():
        session = DeadSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_dead_db
    try:
        db_response = client.get("/api/v1/health/db")
        api_response = client.get("/api/v1/health")
    finally:
        app.dependency_overrides.clear()
        dead_engine.dispose()

    assert db_response.status_code == 503
    assert db_response.json() == {"detail": "Database unavailable"}
    assert api_response.status_code == 200
