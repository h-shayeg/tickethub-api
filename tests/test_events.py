import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking
from app.models.event import Event
from tests.helpers import future, past

EVENTS = "/api/v1/events"

NEW_EVENT = {
    "title": "Rock concert",
    "description": "Live music",
    "starts_at": "2099-06-01T19:30:00Z",
    "price": 2500,
    "total_tickets": 100,
}


# --- Permissions ----------------------------------------------------------


def test_anyone_can_list_and_read_events(client, make_event):
    event = make_event()

    assert client.get(EVENTS).status_code == 200
    assert client.get(f"{EVENTS}/{event.id}").status_code == 200


def test_creating_an_event_needs_a_token(client):
    assert client.post(EVENTS, json=NEW_EVENT).status_code == 401


def test_normal_user_cannot_create_update_or_delete(client, user_headers, make_event):
    event = make_event()

    assert client.post(EVENTS, json=NEW_EVENT, headers=user_headers).status_code == 403
    assert (
        client.patch(
            f"{EVENTS}/{event.id}", json={"title": "Hacked"}, headers=user_headers
        ).status_code
        == 403
    )
    assert client.delete(f"{EVENTS}/{event.id}", headers=user_headers).status_code == 403


def test_normal_user_gets_403_even_for_missing_ids(client, user_headers):
    """A normal user cannot tell which event ids exist."""
    assert client.patch(f"{EVENTS}/999", json={"title": "x"}, headers=user_headers).status_code == 403
    assert client.delete(f"{EVENTS}/999", headers=user_headers).status_code == 403


# --- Create ---------------------------------------------------------------


def test_admin_creates_event_with_all_tickets_available(client, admin_headers):
    response = client.post(EVENTS, json=NEW_EVENT, headers=admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Rock concert"
    assert body["price"] == 2500
    assert body["total_tickets"] == 100
    assert body["available_tickets"] == 100


def test_client_cannot_set_available_tickets(client, admin_headers):
    payload = {**NEW_EVENT, "available_tickets": 1}

    response = client.post(EVENTS, json=payload, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["available_tickets"] == 100


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": "x" * 201},
        {"price": -1},
        {"total_tickets": 0},
        {"starts_at": "2099-06-01T19:30:00"},  # no time zone
        {"starts_at": "not a date"},
    ],
)
def test_create_rejects_invalid_input(client, admin_headers, changes):
    payload = {**NEW_EVENT, **changes}

    assert client.post(EVENTS, json=payload, headers=admin_headers).status_code == 422


# --- Read -----------------------------------------------------------------


def test_reading_a_missing_event_is_404(client):
    response = client.get(f"{EVENTS}/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


# --- Update ---------------------------------------------------------------


def test_patch_changes_only_the_fields_that_were_sent(client, admin_headers, make_event):
    event = make_event(title="Old title", description="Keep me", price=1000)

    response = client.patch(
        f"{EVENTS}/{event.id}", json={"title": "New title"}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["description"] == "Keep me"
    assert body["price"] == 1000


@pytest.mark.parametrize("field", ["title", "starts_at", "price"])
def test_patch_rejects_null_for_required_fields(client, admin_headers, make_event, field):
    event = make_event()

    response = client.patch(
        f"{EVENTS}/{event.id}", json={field: None}, headers=admin_headers
    )

    assert response.status_code == 422


def test_patch_can_clear_the_description(client, admin_headers, make_event):
    event = make_event(description="Something")

    response = client.patch(
        f"{EVENTS}/{event.id}", json={"description": None}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_patch_cannot_change_ticket_counts(client, admin_headers, make_event):
    event = make_event(total_tickets=10)

    response = client.patch(
        f"{EVENTS}/{event.id}",
        json={"total_tickets": 500, "available_tickets": 500},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["total_tickets"] == 10
    assert response.json()["available_tickets"] == 10


def test_patch_missing_event_is_404_for_admin(client, admin_headers):
    response = client.patch(f"{EVENTS}/999", json={"title": "x"}, headers=admin_headers)

    assert response.status_code == 404


# --- Delete ---------------------------------------------------------------


def test_admin_deletes_an_event_without_bookings(client, admin_headers, make_event):
    event = make_event()

    response = client.delete(f"{EVENTS}/{event.id}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"{EVENTS}/{event.id}").status_code == 404


def test_event_with_bookings_cannot_be_deleted(
    client, admin_headers, make_event, make_user, db
):
    event = make_event()
    user = make_user()
    db.add(Booking(user_id=user.id, event_id=event.id, quantity=1, total_price=1000))
    db.commit()

    response = client.delete(f"{EVENTS}/{event.id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json() == {"detail": "Event has bookings and cannot be deleted"}
    assert client.get(f"{EVENTS}/{event.id}").status_code == 200


def test_delete_missing_event_is_404_for_admin(client, admin_headers):
    assert client.delete(f"{EVENTS}/999", headers=admin_headers).status_code == 404


# --- List: pagination -----------------------------------------------------


def test_list_is_paginated_and_reports_the_total(client, make_event):
    for day in range(1, 6):
        make_event(title=f"Event {day}", starts_at=future(days=day))

    response = client.get(EVENTS, params={"limit": 2, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert [e["title"] for e in body["items"]] == ["Event 1", "Event 2"]


def test_pages_cover_every_event_exactly_once(client, make_event):
    same_time = future(days=3)
    for i in range(7):
        # Many events at the same time: the id tie-breaker keeps the order stable.
        make_event(title=f"Event {i}", starts_at=same_time)

    seen = []
    for offset in range(0, 7, 3):
        page = client.get(EVENTS, params={"limit": 3, "offset": offset}).json()
        seen.extend(e["id"] for e in page["items"])

    assert len(seen) == 7
    assert len(set(seen)) == 7
    assert seen == sorted(seen)


def test_list_is_ordered_by_start_time(client, make_event):
    make_event(title="Later", starts_at=future(days=10))
    make_event(title="Sooner", starts_at=future(days=1))

    items = client.get(EVENTS).json()["items"]

    assert [e["title"] for e in items] == ["Sooner", "Later"]


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": "x" * 101}],
)
def test_list_rejects_invalid_parameters(client, params):
    assert client.get(EVENTS, params=params).status_code == 422


# --- List: filters --------------------------------------------------------


def test_search_is_case_insensitive(client, make_event):
    make_event(title="Tehran Jazz Festival")
    make_event(title="Rock Night")

    body = client.get(EVENTS, params={"q": "jazz"}).json()

    assert body["total"] == 1
    assert body["items"][0]["title"] == "Tehran Jazz Festival"


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_search_treats_wildcards_as_plain_text(client, make_event, wildcard):
    make_event(title=f"100{wildcard} fun")
    make_event(title="Plain title")

    body = client.get(EVENTS, params={"q": wildcard}).json()

    assert [e["title"] for e in body["items"]] == [f"100{wildcard} fun"]


def test_upcoming_hides_past_events(client, make_event):
    make_event(title="Yesterday", starts_at=past(days=1))
    make_event(title="Tomorrow", starts_at=future(days=1))

    everything = client.get(EVENTS).json()
    upcoming = client.get(EVENTS, params={"upcoming": True}).json()

    assert everything["total"] == 2
    assert upcoming["total"] == 1
    assert upcoming["items"][0]["title"] == "Tomorrow"


def test_available_only_hides_sold_out_events(client, make_event):
    make_event(title="Sold out", total_tickets=10, available_tickets=0)
    make_event(title="Has seats", total_tickets=10, available_tickets=3)

    body = client.get(EVENTS, params={"available_only": True}).json()

    assert body["total"] == 1
    assert body["items"][0]["title"] == "Has seats"


def test_total_matches_the_filtered_result(client, make_event):
    for i in range(4):
        make_event(title=f"Jazz {i}")
    make_event(title="Rock")

    body = client.get(EVENTS, params={"q": "jazz", "limit": 2}).json()

    assert body["total"] == 4
    assert len(body["items"]) == 2


# --- Database rules -------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"available_tickets": -1},
        {"available_tickets": 11},  # more than total_tickets
        {"price": -5},
    ],
)
def test_database_rejects_impossible_events(db, values):
    """CHECK constraints hold even if application code has a bug."""
    fields = {
        "title": "Broken",
        "starts_at": future(),
        "price": 100,
        "total_tickets": 10,
        "available_tickets": 10,
        **values,
    }
    db.add(Event(**fields))

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
