from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.event import Event


class EventNotFound(Exception):
    pass


class EventAlreadyStarted(Exception):
    pass


class NotEnoughTickets(Exception):
    pass


class BookingNotFound(Exception):
    pass


class BookingAlreadyCancelled(Exception):
    pass


def create_booking(db: Session, user_id: int, event_id: int, quantity: int) -> Booking:
    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    reserve = (
        update(Event)
        .where(
            Event.id == event_id,
            Event.available_tickets >= quantity,
            Event.starts_at > func.now(),
        )
        .values(available_tickets=Event.available_tickets - quantity)
        .returning(Event.price)
        .execution_options(synchronize_session=False)
    )
    price = db.scalar(reserve)

    if price is None:
        db.rollback()
        still_upcoming = db.scalar(
            select(Event.starts_at > func.now()).where(Event.id == event_id)
        )
        if still_upcoming is None:
            raise EventNotFound()
        if not still_upcoming:
            raise EventAlreadyStarted()
        raise NotEnoughTickets()

    booking = Booking(
        user_id=user_id,
        event_id=event_id,
        quantity=quantity,
        total_price=price * quantity,
    )
    db.add(booking)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, user_id: int, booking_id: int) -> Booking:
    cancel = (
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.user_id == user_id,
            Booking.status == "confirmed",
            Booking.event_id.in_(
                select(Event.id).where(Event.starts_at > func.now())
            ),
        )
        .values(status="cancelled")
        .returning(Booking.event_id, Booking.quantity)
        .execution_options(synchronize_session=False)
    )
    row = db.execute(cancel).first()

    if row is None:
        db.rollback()
        found = db.execute(
            select(Booking.status, Event.starts_at > func.now())
            .select_from(Booking)
            .join(Event, Event.id == Booking.event_id)
            .where(Booking.id == booking_id, Booking.user_id == user_id)
        ).first()
        if found is None:
            raise BookingNotFound()
        status, upcoming = found
        if status != "confirmed":
            raise BookingAlreadyCancelled()
        raise EventAlreadyStarted()

    event_id, quantity = row
    db.execute(
        update(Event)
        .where(Event.id == event_id)
        .values(available_tickets=Event.available_tickets + quantity)
        .execution_options(synchronize_session=False)
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return db.get(Booking, booking_id)


def list_user_bookings(
    db: Session, user_id: int, limit: int, offset: int
) -> tuple[list[Booking], int]:
    total = db.scalar(
        select(func.count()).select_from(Booking).where(Booking.user_id == user_id)
    )
    items = db.scalars(
        select(Booking)
        .where(Booking.user_id == user_id)
        .order_by(Booking.created_at.desc(), Booking.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total
