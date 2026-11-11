from datetime import timedelta

from app.views import event_view


def test_event_view_shape(make_event, now):
    ev = make_event(tags=["food"], group="ACM", author_handle="acm.bsky.social")
    view = event_view(ev, now)
    assert set(view) == {
        "uri", "cid", "authorDid", "authorHandle", "source", "name", "description",
        "startsAt", "endsAt", "location", "tags", "group", "sourceUrl", "indexedAt",
        "updatedAt", "status", "createdAt",
    }  # fmt: skip
    assert view["authorHandle"] == "acm.bsky.social"
    assert view["location"] == {
        "name": "Price Center", "address": None, "lat": "32.8797", "lng": "-117.2362",
    }  # fmt: skip
    assert view["tags"] == ["food"]
    assert isinstance(view["startsAt"], str)


def test_status(make_event, now):
    assert event_view(make_event(start_h=1, end_h=2), now)["status"] == "upcoming"
    assert event_view(make_event(start_h=-1, end_h=2), now)["status"] == "live"
    assert event_view(make_event(start_h=-1, end_h=0.5), now)["status"] == "ending_soon"
    assert event_view(make_event(start_h=0, end_h=1), now)["status"] == "ending_soon"


def test_status_naive_now(make_event, now):
    naive = (now + timedelta(minutes=1)).replace(tzinfo=None)
    assert event_view(make_event(start_h=0, end_h=3), naive)["status"] == "live"
