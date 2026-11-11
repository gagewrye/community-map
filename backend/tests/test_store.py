from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Count,
    EventQuery,
    EventUpdate,
    Listener,
    ListenerRecord,
    Notification,
)
from app.seed import seed
from app.store.sqlite import SqliteStore, to_iso


def uris(page):
    return [e.uri.rsplit("/", 1)[1] for e in page.events]


def test_upsert_created_updated_unchanged(store, make_event):
    ev = make_event()
    assert store.upsert_event(ev) == "created"
    assert store.upsert_event(ev) == "unchanged"
    assert store.upsert_event(ev.model_copy(update={"cid": "bafy2"})) == "updated"
    changed = make_event(name="Renamed", cid="bafy2")
    assert store.upsert_event(changed) == "updated"
    assert store.get_event(ev.uri).record.name == "Renamed"


def test_update_keeps_original_indexed_at(store, make_event, now):
    store.upsert_event(make_event())
    later = make_event(name="New", cid="bafy2", indexed_at=now + timedelta(hours=1))
    store.upsert_event(later)
    assert store.get_event(later.uri).indexed_at == now


def test_get_event_roundtrip(store, make_event):
    ev = make_event(tags=["food"], group="ACM", author_handle="a.bsky.social")
    store.upsert_event(ev)
    assert store.get_event(ev.uri) == ev
    assert store.get_event("at://nope") is None


def test_delete_event(store, make_event):
    ev = make_event(tags=["food"])
    store.upsert_event(ev)
    store.subscribe("subscriber1", ev.uri)
    assert store.delete_event(ev.uri) is True
    assert store.subscribers_of(ev.uri) == []
    assert store.delete_event(ev.uri) is False
    assert store.get_event(ev.uri) is None
    assert store.list_tags(datetime.now(UTC)) == []


def test_query_hides_expired_and_orders(store, make_event, now):
    store.upsert_event(make_event("b", start_h=2, end_h=3))
    store.upsert_event(make_event("a", start_h=2, end_h=3))
    store.upsert_event(make_event("c", start_h=-1, end_h=1))
    store.upsert_event(make_event("old", start_h=-3, end_h=-2))
    assert uris(store.query_events(EventQuery(), now)) == ["c", "a", "b"]
    q = EventQuery(ends_after=now - timedelta(hours=5))
    assert uris(store.query_events(q, now)) == ["old", "c", "a", "b"]


def test_query_filters(store, make_event, now):
    store.upsert_event(make_event("1", tags=["food", "free"], group="ACM", name="Pizza Night"))
    store.upsert_event(make_event("2", tags=["music"], description="Live JAZZ band"))
    store.upsert_event(
        make_event("3", tags=["tech"], location="Geisel Library", start_h=10, end_h=11)
    )
    assert uris(store.query_events(EventQuery(tags=["music", "free"]), now)) == ["1", "2"]
    assert uris(store.query_events(EventQuery(tags=["#Food"]), now)) == ["1"]
    assert uris(store.query_events(EventQuery(group="ACM"), now)) == ["1"]
    assert uris(store.query_events(EventQuery(group="acm"), now)) == []
    assert uris(store.query_events(EventQuery(text="pizza"), now)) == ["1"]
    assert uris(store.query_events(EventQuery(text="jazz"), now)) == ["2"]
    assert uris(store.query_events(EventQuery(text="geisel"), now)) == ["3"]
    before = EventQuery(starts_before=now + timedelta(hours=5))
    assert uris(store.query_events(before, now)) == ["1", "2"]


def test_query_pagination(store, make_event, now):
    for i in range(5):
        store.upsert_event(make_event(f"e{i}", start_h=1 + i // 2, end_h=10))
    seen: list[str] = []
    q = EventQuery(limit=2)
    while True:
        page = store.query_events(q, now)
        seen += uris(page)
        if page.cursor is None:
            break
        q = q.model_copy(update={"cursor": page.cursor})
    assert seen == ["e0", "e1", "e2", "e3", "e4"]


def test_query_exact_page_has_no_cursor(store, make_event, now):
    store.upsert_event(make_event("a"))
    store.upsert_event(make_event("b"))
    assert store.query_events(EventQuery(limit=2), now).cursor is None


def test_query_bad_cursor(store, now):
    with pytest.raises(ValueError):
        store.query_events(EventQuery(cursor="!!!not-base64"), now)
    with pytest.raises(ValueError):
        store.query_events(EventQuery(cursor="bm9waXBl"), now)  # "nopipe"


def test_naive_datetimes_are_utc(store, make_event, now):
    store.upsert_event(make_event("a", start_h=-1, end_h=1))
    naive_now = now.astimezone(UTC).replace(tzinfo=None)
    assert uris(store.query_events(EventQuery(), naive_now)) == ["a"]
    assert to_iso(naive_now) == to_iso(now)


def test_delete_expired_cascades(store, make_event, now):
    old = make_event("old", start_h=-3, end_h=-1, tags=["food"])
    live = make_event("live", start_h=-1, end_h=1, tags=["food"])
    store.upsert_event(old)
    store.upsert_event(live)
    store.subscribe("subscriber1", old.uri)
    store.subscribe("subscriber1", live.uri)
    store.add_update(EventUpdate(event_uri=old.uri, text="hi", created_at=now))
    assert store.delete_expired(now) == [old.uri]
    assert store.get_event(old.uri) is None
    assert store.list_updates(old.uri) == []
    assert store.subscriptions_of("subscriber1") == [live.uri]
    assert store.list_tags(now - timedelta(hours=5)) == [Count(value="food", count=1)]


def test_list_tags_and_groups(store, make_event, now):
    store.upsert_event(make_event("1", tags=["food", "free"], group="ACM"))
    store.upsert_event(make_event("2", tags=["free", "music"], group="KSDT"))
    store.upsert_event(make_event("3", tags=["free"], group="ACM"))
    store.upsert_event(make_event("x", tags=["zzz"], group="Gone", start_h=-3, end_h=-2))
    assert store.list_tags(now) == [
        Count(value="free", count=3),
        Count(value="food", count=1),
        Count(value="music", count=1),
    ]
    assert store.list_groups(now) == [Count(value="ACM", count=2), Count(value="KSDT", count=1)]


def test_updates(store, now):
    store.add_update(EventUpdate(event_uri="u", text="2nd", created_at=now + timedelta(1)))
    store.add_update(EventUpdate(event_uri="u", text="1st", source_uri="at://p", created_at=now))
    got = store.list_updates("u")
    assert [u.text for u in got] == ["1st", "2nd"]
    assert got[0].source_uri == "at://p"
    assert got[0].created_at == now


def test_listeners(store, now):
    rec = ListenerRecord(subject="at://did:a/x/1", hashtag="#Party", created_at=now)
    store.upsert_listener(Listener(uri="at://did:a/l/1", author_did="did:a", record=rec))
    store.upsert_listener(Listener(uri="at://did:b/l/1", author_did="did:b", record=rec))
    assert store.listener_dids() == ["did:a", "did:b"]
    [got] = store.listeners_for_did("did:a")
    assert got.record.hashtag == "party"
    assert store.delete_listener("at://did:a/l/1") is True
    assert store.delete_listener("at://did:a/l/1") is False
    assert store.listener_dids() == ["did:b"]


def test_subscriptions(store):
    store.subscribe("sub-a", "at://e1")
    store.subscribe("sub-a", "at://e1")
    store.subscribe("sub-b", "at://e1")
    store.subscribe("sub-a", "at://e2")
    assert store.subscribers_of("at://e1") == ["sub-a", "sub-b"]
    assert store.subscriptions_of("sub-a") == ["at://e1", "at://e2"]
    store.unsubscribe("sub-a", "at://e1")
    assert store.subscribers_of("at://e1") == ["sub-b"]


def test_notifications(store, now):
    def make(sub: str) -> Notification:
        return Notification(
            subscriber_id=sub, event_uri="at://e", kind="updated", message="m", created_at=now
        )

    a1 = store.add_notification(make("a"))
    store.add_notification(make("b"))
    a2 = store.add_notification(make("a"))
    assert a1.id is not None and a2.id > a1.id
    assert store.list_notifications("a") == [a1, a2]
    assert store.list_notifications("a", since_id=a1.id) == [a2]


def test_cursors(store):
    assert store.get_cursor("jetstream") is None
    store.set_cursor("jetstream", 5)
    store.set_cursor("jetstream", 7)
    assert store.get_cursor("jetstream") == 7


def test_file_store_persists(tmp_path, make_event):
    path = str(tmp_path / "sub" / "db.sqlite")
    s = SqliteStore(path)
    s.upsert_event(make_event())
    s.close()
    s2 = SqliteStore(path)
    assert s2.get_event(make_event().uri) is not None
    s2.close()


def test_seed(store, now):
    assert seed(store, now) == 12
    page = store.query_events(EventQuery(limit=100), now)
    assert len(page.events) == 12
    live = [e for e in page.events if e.record.starts_at <= now <= e.record.ends_at]
    assert len(live) >= 2
    assert any(e.record.ends_at - now <= timedelta(hours=1) for e in live)
    assert all(e.record.starts_at < now + timedelta(days=7) for e in page.events)
