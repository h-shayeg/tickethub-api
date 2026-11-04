from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token
from app.models.user import User


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def future(days: float = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def past(days: float = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
