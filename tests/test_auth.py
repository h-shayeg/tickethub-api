from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import ALGORITHM
from app.services.user import get_user_by_email
from tests.helpers import auth_headers

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/users/me"


def login(client, email: str, password: str):
    return client.post(LOGIN, data={"username": email, "password": password})


# --- Registration ---------------------------------------------------------


def test_register_creates_a_normal_user(client):
    response = client.post(
        REGISTER, json={"email": "ali@example.com", "password": "long-enough"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ali@example.com"
    assert body["role"] == "user"
    assert "hashed_password" not in body
    assert "password" not in body


def test_register_ignores_a_role_sent_by_the_client(client):
    response = client.post(
        REGISTER,
        json={"email": "sneaky@example.com", "password": "long-enough", "role": "admin"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_register_stores_email_in_lowercase(client):
    response = client.post(
        REGISTER, json={"email": "Ali@Example.COM", "password": "long-enough"}
    )

    assert response.status_code == 201
    assert response.json()["email"] == "ali@example.com"


def test_register_rejects_duplicate_email_in_any_case(client):
    client.post(REGISTER, json={"email": "ali@example.com", "password": "long-enough"})

    response = client.post(
        REGISTER, json={"email": "ALI@example.com", "password": "another-one"}
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Email already registered"}


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "long-enough"},
        {"email": "ali@example.com", "password": "short"},
        {"email": "ali@example.com", "password": "x" * 129},
        {"email": "ali@example.com"},
    ],
)
def test_register_rejects_invalid_input(client, payload):
    assert client.post(REGISTER, json=payload).status_code == 422


def test_password_is_stored_as_a_hash(client, db):
    client.post(REGISTER, json={"email": "ali@example.com", "password": "long-enough"})

    user = get_user_by_email(db, "ali@example.com")
    assert user.hashed_password != "long-enough"
    assert user.hashed_password.startswith("$argon2")


# --- Login ------------------------------------------------------------------


def test_login_returns_a_token_that_works(client, make_user):
    make_user(email="ali@example.com", password="long-enough")

    response = login(client, "ali@example.com", "long-enough")

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    me = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ali@example.com"


def test_login_email_is_case_insensitive(client, make_user):
    make_user(email="ali@example.com", password="long-enough")

    assert login(client, "ALI@Example.com", "long-enough").status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client, make_user):
    make_user(email="ali@example.com", password="long-enough")

    wrong_password = login(client, "ali@example.com", "wrong-password")
    unknown_email = login(client, "nobody@example.com", "long-enough")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


# --- Tokens ---------------------------------------------------------------


def make_token(payload: dict, key: str | None = None, algorithm: str = ALGORITHM) -> str:
    return jwt.encode(payload, key or settings.secret_key, algorithm=algorithm)


def in_minutes(minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def test_me_without_token_is_401(client):
    assert client.get(ME).status_code == 401


def test_me_returns_the_current_user(client, make_user):
    user = make_user(email="ali@example.com")

    response = client.get(ME, headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()["id"] == user.id


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda uid: "not.a.jwt", id="garbage"),
        pytest.param(
            lambda uid: make_token({"sub": str(uid), "exp": in_minutes(-1)}),
            id="expired",
        ),
        pytest.param(lambda uid: make_token({"sub": str(uid)}), id="no-exp"),
        pytest.param(lambda uid: make_token({"exp": in_minutes(5)}), id="no-sub"),
        pytest.param(
            lambda uid: make_token({"sub": "abc", "exp": in_minutes(5)}),
            id="sub-not-a-number",
        ),
        pytest.param(
            lambda uid: make_token({"sub": "999999", "exp": in_minutes(5)}),
            id="user-does-not-exist",
        ),
        pytest.param(
            lambda uid: make_token(
                {"sub": str(uid), "exp": in_minutes(5)},
                key="a-different-secret-key-that-is-long-enough",
            ),
            id="wrong-signature",
        ),
        pytest.param(
            lambda uid: make_token(
                {"sub": str(uid), "exp": in_minutes(5)}, algorithm="HS512"
            ),
            id="other-algorithm",
        ),
        pytest.param(
            lambda uid: jwt.encode(
                {"sub": str(uid), "exp": in_minutes(5)}, None, algorithm="none"
            ),
            id="unsigned",
        ),
    ],
)
def test_bad_tokens_are_rejected_with_401(client, make_user, token_factory):
    user = make_user()

    response = client.get(
        ME, headers={"Authorization": f"Bearer {token_factory(user.id)}"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_role_change_applies_to_an_existing_token(client, make_user, db):
    """The role is read from the database on every request, not from the token."""
    user = make_user()
    headers = auth_headers(user)
    event = {
        "title": "Jazz night",
        "starts_at": "2099-01-01T20:00:00Z",
        "price": 500,
        "total_tickets": 10,
    }
    assert client.post("/api/v1/events", json=event, headers=headers).status_code == 403

    user.role = "admin"
    db.commit()

    assert client.post("/api/v1/events", json=event, headers=headers).status_code == 201
