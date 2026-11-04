import pytest
from sqlalchemy.exc import IntegrityError

from app.cli import main
from app.models.user import User
from tests.helpers import auth_headers

NEW_EVENT = {
    "title": "Opening night",
    "starts_at": "2099-01-01T20:00:00Z",
    "price": 100,
    "total_tickets": 5,
}


def role_of(db, user: User) -> str:
    db.expire_all()
    return db.get(User, user.id).role


def test_make_admin_gives_admin_rights(client, db, make_user, capsys):
    user = make_user(email="boss@example.com")

    exit_code = main(["make-admin", "boss@example.com"])

    assert exit_code == 0
    assert "boss@example.com is now 'admin'" in capsys.readouterr().out
    assert role_of(db, user) == "admin"
    response = client.post(
        "/api/v1/events", json=NEW_EVENT, headers=auth_headers(user)
    )
    assert response.status_code == 201


def test_remove_admin_takes_admin_rights_away(client, db, make_user):
    user = make_user(email="boss@example.com", role="admin")

    assert main(["remove-admin", "boss@example.com"]) == 0

    assert role_of(db, user) == "user"
    response = client.post(
        "/api/v1/events", json=NEW_EVENT, headers=auth_headers(user)
    )
    assert response.status_code == 403


def test_email_is_matched_case_insensitively(db, make_user):
    user = make_user(email="boss@example.com")

    assert main(["make-admin", "  BOSS@Example.com "]) == 0

    assert role_of(db, user) == "admin"


def test_unknown_email_fails_with_a_clear_message(capsys):
    exit_code = main(["make-admin", "nobody@example.com"])

    assert exit_code == 1
    assert "No user with email nobody@example.com" in capsys.readouterr().err


def test_a_command_is_required():
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2


def test_database_rejects_unknown_roles(db, make_user):
    user = make_user()
    user.role = "superadmin"

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
