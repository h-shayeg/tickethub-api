from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.event import Event
from app.schemas.event import EventCreate, EventPage, EventRead, EventUpdate
from app.services.event import (
    EventHasBookings,
    create_event,
    delete_event,
    get_event,
    list_events,
    update_event,
)

router = APIRouter(prefix="/events", tags=["events"])


def get_event_or_404(db: Session, event_id: int) -> Event:
    event = get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return event


@router.get("", response_model=EventPage)
def read_many(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=100),
    upcoming: bool = False,
    available_only: bool = False,
    db: Session = Depends(get_db),
):
    items, total = list_events(
        db,
        limit=limit,
        offset=offset,
        q=q,
        upcoming=upcoming,
        available_only=available_only,
    )
    return EventPage(
        items=[EventRead.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create(data: EventCreate, db: Session = Depends(get_db)):
    return create_event(db, data)


@router.get("/{event_id}", response_model=EventRead)
def read(event_id: int, db: Session = Depends(get_db)):
    return get_event_or_404(db, event_id)


@router.patch(
    "/{event_id}",
    response_model=EventRead,
    dependencies=[Depends(require_admin)],
)
def update(event_id: int, data: EventUpdate, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    return update_event(db, event, data)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def delete(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    try:
        delete_event(db, event)
    except EventHasBookings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event has bookings and cannot be deleted",
        )
