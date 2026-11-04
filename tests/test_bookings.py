import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking
from app.models.event import Event
from tests.helpers import auth_headers, past

BOOKINGS = "/api/v1/bookings"
EVENTS = "/api/v1/events"


def book(client, headers, event_id: int, quantity: int = 1):
    return client.post(
        BOOKINGS, json={"event_id": event_id, "quantity": quantity}, headers=headers
    )


def available(db, event_id: int) -> int:
    db.expire_all()
    return db.get(Event, event_id).available_tickets


# --- Create ---------------------------------------------------------------


def test_booking_needs_a_token(client, make_event):
    event = make_event()

    response = client.post(BOOKINGS, json={"event_id": event.id, "quantity": 1})

    assert response.status_code == 401


def test_booking_reserves_tickets_and_charges_the_event_price(
    client, make_user, make_event, db
):
    user = make_user()
    event = make_event(price=1500, total_tickets=10)

    response = book(client, auth_headers(user), event.id, quantity=3)

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user.id
    assert body["event_id"] == event.id
    assert body["quantity"] == 3
    assert body["total_price"] == 4500
    assert body["status"] == "confirmed"
    assert available(db, event.id) == 7


def test_client_cannot_choose_owner_or_price(client, make_user, make_event):
    user = make_user()
    other = make_user()
    event = make_event(price=1000)

    response = client.post(
        BOOKINGS,
        json={
            "event_id": event.id,
            "quantity": 2,
            "user_id": other.id,
            "total_price": 0,
        },
        headers=auth_headers(user),
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == user.id
    assert response.json()["total_price"] == 2000


def test_free_event_has_price_zero(client, user_headers, make_event):
    event = make_event(price=0)

    response = book(client, user_headers, event.id, quantity=2)

    assert response.status_code == 201
    assert response.json()["total_price"] == 0


def test_buying_the_last_tickets_works(client, user_headers, make_event, db):
    event = make_event(total_tickets=10, available_tickets=4)

    response = book(client, user_headers, event.id, quantity=4)

    assert response.status_code == 201
    assert available(db, event.id) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"event_id": 1, "quantity": 0},
        {"event_id": 1, "quantity": 11},
        {"event_id": 0, "quantity": 1},
        {"event_id": 1},
    ],
)
def test_invalid_booking_input_is_422(client, user_headers, payload):
    assert client.post(BOOKINGS, json=payload, headers=user_headers).status_code == 422


def test_booking_a_missing_event_is_404(client, user_headers):
    response = book(client, user_headers, event_id=999)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


def test_booking_a_started_event_is_409(client, user_headers, make_event, db):
    event = make_event(starts_at=past(days=1), total_tickets=10)

    response = book(client, user_headers, event.id)

    assert response.status_code == 409
    assert response.json() == {"detail": "Event has already started"}
    assert available(db, event.id) == 10


def test_not_enough_tickets_is_409_and_changes_nothing(
    client, user_headers, make_event, db
):
    event = make_event(total_tickets=10, available_tickets=2)

    response = book(client, user_headers, event.id, quantity=3)

    assert response.status_code == 409
    assert response.json() == {"detail": "Not enough tickets available"}
    assert available(db, event.id) == 2
    assert db.scalars(select(Booking)).all() == []


def test_a_failed_booking_does_not_block_the_next_one(client, user_headers, make_event):
    event = make_event(total_tickets=10, available_tickets=2)

    assert book(client, user_headers, event.id, quantity=5).status_code == 409
    assert book(client, user_headers, event.id, quantity=2).status_code == 201


def test_total_price_is_a_snapshot(client, user_headers, admin_headers, make_event):
    event = make_event(price=1000)
    booking = book(client, user_headers, event.id, quantity=2).json()

    client.patch(f"{EVENTS}/{event.id}", json={"price": 9999}, headers=admin_headers)

    listed = client.get(BOOKINGS, headers=user_headers).json()["items"][0]
    assert listed["id"] == booking["id"]
    assert listed["total_price"] == 2000


# --- List -----------------------------------------------------------------


def test_users_only_see_their_own_bookings(client, make_user, make_event):
    ali, sara = make_user(), make_user()
    event = make_event()
    book(client, auth_headers(ali), event.id)
    book(client, auth_headers(sara), event.id)
    book(client, auth_headers(sara), event.id)

    ali_list = client.get(BOOKINGS, headers=auth_headers(ali)).json()
    sara_list = client.get(BOOKINGS, headers=auth_headers(sara)).json()

    assert ali_list["total"] == 1
    assert sara_list["total"] == 2
    assert {b["user_id"] for b in sara_list["items"]} == {sara.id}


def test_bookings_list_is_newest_first_and_paginated(client, user_headers, make_event):
    event = make_event()
    ids = [book(client, user_headers, event.id).json()["id"] for _ in range(3)]

    page = client.get(BOOKINGS, params={"limit": 2}, headers=user_headers).json()

    assert page["total"] == 3
    assert [b["id"] for b in page["items"]] == [ids[2], ids[1]]


def test_bookings_list_needs_a_token(client):
    assert client.get(BOOKINGS).status_code == 401


# --- Cancel ---------------------------------------------------------------


def test_cancel_returns_the_tickets(client, user_headers, make_event, db):
    event = make_event(total_tickets=10)
    booking = book(client, user_headers, event.id, quantity=3).json()

    response = client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert available(db, event.id) == 10


def test_cancelled_booking_stays_in_the_list(client, user_headers, make_event):
    event = make_event()
    booking = book(client, user_headers, event.id).json()
    client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=user_headers)

    items = client.get(BOOKINGS, headers=user_headers).json()["items"]

    assert [(b["id"], b["status"]) for b in items] == [(booking["id"], "cancelled")]


def test_cancelling_twice_is_409(client, user_headers, make_event, db):
    event = make_event(total_tickets=10)
    booking = book(client, user_headers, event.id, quantity=3).json()
    client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=user_headers)

    response = client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=user_headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Booking is already cancelled"}
    assert available(db, event.id) == 10


def test_cannot_cancel_someone_elses_booking(client, make_user, make_event, db):
    owner, stranger = make_user(), make_user()
    event = make_event(total_tickets=10)
    booking = book(client, auth_headers(owner), event.id, quantity=2).json()

    response = client.post(
        f"{BOOKINGS}/{booking['id']}/cancel", headers=auth_headers(stranger)
    )

    # Same answer as a booking that does not exist, so ids cannot be probed.
    assert response.status_code == 404
    assert response.json() == {"detail": "Booking not found"}
    assert available(db, event.id) == 8


def test_cancelling_a_missing_booking_is_404(client, user_headers):
    assert client.post(f"{BOOKINGS}/999/cancel", headers=user_headers).status_code == 404


def test_cannot_cancel_after_the_event_started(
    client, user_headers, admin_headers, make_event, db
):
    event = make_event(total_tickets=10)
    booking = book(client, user_headers, event.id, quantity=2).json()
    client.patch(
        f"{EVENTS}/{event.id}",
        json={"starts_at": past(days=1).isoformat()},
        headers=admin_headers,
    )

    response = client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=user_headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Event has already started"}
    assert available(db, event.id) == 8


# --- Database rules -------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [{"quantity": 0}, {"total_price": -1}, {"status": "refunded"}],
)
def test_database_rejects_impossible_bookings(db, make_user, make_event, values):
    user = make_user()
    event = make_event()
    fields = {
        "user_id": user.id,
        "event_id": event.id,
        "quantity": 1,
        "total_price": 100,
        **values,
    }
    db.add(Booking(**fields))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_user_with_bookings_cannot_be_deleted(db, make_user, make_event):
    user = make_user()
    event = make_event()
    db.add(Booking(user_id=user.id, event_id=event.id, quantity=1, total_price=100))
    db.commit()

    db.delete(user)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
