from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event
from app.schemas.event import EventCreate, EventUpdate


class EventHasBookings(Exception):
    pass


def create_event(db: Session, data: EventCreate) -> Event:
    event = Event(
        title=data.title,
        description=data.description,
        starts_at=data.starts_at,
        price=data.price,
        total_tickets=data.total_tickets,
        available_tickets=data.total_tickets,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event(db: Session, event_id: int) -> Event | None:
    return db.get(Event, event_id)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_filters(
    stmt: Select,
    q: str | None,
    upcoming: bool,
    available_only: bool,
) -> Select:
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
    if upcoming:
        stmt = stmt.where(Event.starts_at > func.now())
    if available_only:
        stmt = stmt.where(Event.available_tickets > 0)
    return stmt


def list_events(
    db: Session,
    limit: int,
    offset: int,
    q: str | None = None,
    upcoming: bool = False,
    available_only: bool = False,
) -> tuple[list[Event], int]:
    count_stmt = _apply_filters(
        select(func.count()).select_from(Event), q, upcoming, available_only
    )
    total = db.scalar(count_stmt)
    items_stmt = _apply_filters(select(Event), q, upcoming, available_only)
    items = db.scalars(
        items_stmt.order_by(Event.starts_at, Event.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def update_event(db: Session, event: Event, data: EventUpdate) -> Event:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


def delete_event(db: Session, event: Event) -> None:
    db.delete(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EventHasBookings()
