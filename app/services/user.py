from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User


ROLES = ("user", "admin")


class EmailAlreadyRegistered(Exception):
    pass


class UserNotFound(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(db: Session, email: str, password: str) -> User:
    user = User(
        email=normalize_email(email),
        hashed_password=hash_password(password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered()
    db.refresh(user)
    return user


def set_role(db: Session, email: str, role: str) -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    user = get_user_by_email(db, email)
    if user is None:
        raise UserNotFound()
    user.role = role
    db.commit()
    db.refresh(user)
    return user
