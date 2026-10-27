from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingPage, BookingRead
from app.services.booking import (
    BookingAlreadyCancelled,
    BookingNotFound,
    EventAlreadyStarted,
    EventNotFound,
    NotEnoughTickets,
    cancel_booking,
    create_booking,
    list_user_bookings,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create(
    data: BookingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_booking(db, current_user.id, data.event_id, data.quantity)
    except EventNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    except EventAlreadyStarted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event has already started",
        )
    except NotEnoughTickets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Not enough tickets available",
        )


@router.get("", response_model=BookingPage)
def read_many(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = list_user_bookings(db, current_user.id, limit=limit, offset=offset)
    return BookingPage(
        items=[BookingRead.model_validate(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{booking_id}/cancel", response_model=BookingRead)
def cancel(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return cancel_booking(db, current_user.id, booking_id)
    except BookingNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    except BookingAlreadyCancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Booking is already cancelled",
        )
    except EventAlreadyStarted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event has already started",
        )
