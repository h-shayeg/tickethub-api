"""Many requests at the same moment.

These are the automated versions of the manual tests in docs/DECISIONS.md
(Step 6). Each thread opens its own database session, like a real request
would, and a barrier releases all threads at once so they really compete for
the same row.
"""

import threading
from collections import Counter
from collections.abc import Callable

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.booking import Booking
from app.models.event import Event
from app.services.booking import (
    BookingAlreadyCancelled,
    NotEnoughTickets,
    cancel_booking,
    create_booking,
)


def run_at_the_same_time(count: int, work: Callable[[int], str]) -> Counter:
    """Run `work(i)` in `count` threads that all start together."""
    barrier = threading.Barrier(count)
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        barrier.wait()
        try:
            outcome = work(i)
        except Exception as exc:  # recorded, so the test shows what went wrong
            outcome = f"unexpected {type(exc).__name__}: {exc}"
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert len(results) == count, "some threads did not finish"
    return Counter(results)


def test_no_overselling_when_many_users_buy_at_once(db, make_user, make_event):
    event_id = make_event(total_tickets=5).id
    user_ids = [make_user().id for _ in range(12)]

    def try_to_book(i: int) -> str:
        session = SessionLocal()
        try:
            create_booking(session, user_ids[i], event_id, quantity=1)
            return "booked"
        except NotEnoughTickets:
            return "sold out"
        finally:
            session.close()

    outcomes = run_at_the_same_time(12, try_to_book)

    assert outcomes == Counter({"booked": 5, "sold out": 7})
    db.expire_all()
    assert db.get(Event, event_id).available_tickets == 0
    sold = db.scalar(
        select(func.sum(Booking.quantity)).where(Booking.event_id == event_id)
    )
    assert sold == 5


def test_tickets_are_returned_only_once_on_parallel_cancels(db, make_user, make_event):
    user_id = make_user().id
    event_id = make_event(total_tickets=10).id
    # Plain ids, not ORM objects: a session must never be shared between threads.
    booking_id = create_booking(db, user_id, event_id, quantity=3).id

    def try_to_cancel(i: int) -> str:
        session = SessionLocal()
        try:
            cancel_booking(session, user_id, booking_id)
            return "cancelled"
        except BookingAlreadyCancelled:
            return "already cancelled"
        finally:
            session.close()

    outcomes = run_at_the_same_time(8, try_to_cancel)

    assert outcomes == Counter({"cancelled": 1, "already cancelled": 7})
    db.expire_all()
    assert db.get(Event, event_id).available_tickets == 10
