from __future__ import annotations

from typing import Any

import pytest

from app.ingest.processor import CommitProcessor, diff_events, extract_hashtags
from app.models import EVENT_NSID, LISTENER_NSID, POST_NSID, EventRecord
from tests.ingest_fakes import FakeNotifier, FakeResolver, FakeStore, utc

DID = "did:plc:alice"
OTHER = "did:plc:mallory"
NOW = utc(2026, 11, 11, 12)
EV_URI = f"at://{DID}/{EVENT_NSID}/ev1"


def event_record(**over: Any) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "name": "Taco Night",
        "description": "Free tacos",
        "startsAt": "2026-11-12T18:00:00Z",
        "endsAt": "2026-11-12T20:00:00Z",
        "location": {"name": "Price Center", "lat": "32.88", "lng": "-117.24"},
        "tags": ["food"],
        "createdAt": "2026-11-11T00:00:00Z",
    }
    rec.update(over)
    return rec


def commit(
    collection: str,
    op: str,
    rkey: str,
    record: dict[str, Any] | None = None,
    did: str = DID,
) -> dict[str, Any]:
    c: dict[str, Any] = {"operation": op, "collection": collection, "rkey": rkey, "cid": "bafy1"}
    if record is not None:
        c["record"] = record
    return {"did": did, "time_us": 1, "kind": "commit", "commit": c}


def listener_record(subject: str = EV_URI, hashtag: str = "#TacoNight") -> dict[str, Any]:
    return {"subject": subject, "hashtag": hashtag, "createdAt": "2026-11-11T00:00:00Z"}


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def notifier(store: FakeStore) -> FakeNotifier:
    return FakeNotifier(store)


@pytest.fixture
def proc(store: FakeStore, notifier: FakeNotifier) -> CommitProcessor:
    return CommitProcessor(store, notifier, clock=lambda: NOW)


# ---- events ---------------------------------------------------------------


async def test_create_event_indexes_it(proc: CommitProcessor, store: FakeStore) -> None:
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    ev = store.get_event(EV_URI)
    assert ev is not None
    assert ev.author_did == DID
    assert ev.source == "atproto"
    assert ev.cid == "bafy1"
    assert ev.record.name == "Taco Night"
    assert ev.indexed_at == NOW and ev.updated_at == NOW


async def test_non_commit_messages_ignored(proc: CommitProcessor, store: FakeStore) -> None:
    await proc.handle({"did": DID, "time_us": 1, "kind": "identity", "identity": {}})
    await proc.handle({"did": DID, "kind": "commit"})  # malformed: no commit body
    assert store.events == {}


async def test_invalid_event_skipped(proc: CommitProcessor, store: FakeStore) -> None:
    bad = event_record(endsAt="2026-11-12T10:00:00Z")  # ends before start
    await proc.handle(commit(EVENT_NSID, "create", "ev1", bad))
    await proc.handle(commit(EVENT_NSID, "create", "ev2", {"name": ""}))
    assert store.events == {}


async def test_update_preserves_indexed_at_and_notifies_diff(
    store: FakeStore, notifier: FakeNotifier
) -> None:
    times = iter([NOW, utc(2026, 11, 11, 13)])
    proc = CommitProcessor(store, notifier, clock=lambda: next(times))
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    moved = event_record(location={"name": "Sun God Lawn"})
    await proc.handle(commit(EVENT_NSID, "update", "ev1", moved))
    ev = store.get_event(EV_URI)
    assert ev is not None
    assert ev.indexed_at == NOW
    assert ev.updated_at == utc(2026, 11, 11, 13)
    assert notifier.published == [
        (EV_URI, "updated", "Location changed: Price Center → Sun God Lawn")
    ]


async def test_unchanged_update_does_not_notify(
    proc: CommitProcessor, notifier: FakeNotifier
) -> None:
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    await proc.handle(commit(EVENT_NSID, "update", "ev1", event_record()))
    assert notifier.published == []


async def test_delete_publishes_before_deleting(
    proc: CommitProcessor, store: FakeStore, notifier: FakeNotifier
) -> None:
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    await proc.handle(commit(EVENT_NSID, "delete", "ev1"))
    assert store.get_event(EV_URI) is None
    assert notifier.published == [(EV_URI, "deleted", "Taco Night was cancelled")]
    assert notifier.event_present == [True]


async def test_delete_unknown_event_is_noop(proc: CommitProcessor, notifier: FakeNotifier) -> None:
    await proc.handle(commit(EVENT_NSID, "delete", "nope"))
    assert notifier.published == []


async def test_handle_resolved_on_create_and_reused(
    store: FakeStore, notifier: FakeNotifier
) -> None:
    resolver = FakeResolver({DID: "alice.test"})
    proc = CommitProcessor(store, notifier, handle_resolver=resolver, clock=lambda: NOW)
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    await proc.handle(commit(EVENT_NSID, "update", "ev1", event_record(name="Taco Fest")))
    ev = store.get_event(EV_URI)
    assert ev is not None and ev.author_handle == "alice.test"
    assert resolver.calls == [DID]


# ---- diff -----------------------------------------------------------------


def test_diff_events_reports_each_change() -> None:
    old = EventRecord.model_validate(event_record())
    new = EventRecord.model_validate(
        event_record(
            name="Taco Fest",
            description="Free tacos and salsa",
            startsAt="2026-11-12T19:00:00Z",
            endsAt="2026-11-12T21:00:00Z",
            tags=["food", "music"],
            group="Taco Club",
        )
    )
    diffs = diff_events(old, new)
    assert diffs[0] == "Name changed: Taco Night → Taco Fest"
    assert diffs[1].startswith("Time changed: ")
    assert "→" in diffs[1]
    assert "Description updated" in diffs
    assert "Tags changed: food → food, music" in diffs
    assert "Group changed: none → Taco Club" in diffs


def test_diff_events_location_details() -> None:
    old = EventRecord.model_validate(event_record())
    new = EventRecord.model_validate(
        event_record(location={"name": "Price Center", "lat": "32.9", "lng": "-117.2"})
    )
    assert diff_events(old, new) == ["Location details updated"]
    assert diff_events(old, old) == []


# ---- listeners ------------------------------------------------------------


async def test_listener_upserted_for_own_event(proc: CommitProcessor, store: FakeStore) -> None:
    await proc.handle(commit(LISTENER_NSID, "create", "l1", listener_record()))
    (li,) = store.listeners.values()
    assert li.uri == f"at://{DID}/{LISTENER_NSID}/l1"
    assert li.record.hashtag == "taconight"
    assert li.author_did == DID


async def test_listener_for_someone_elses_event_rejected(
    proc: CommitProcessor, store: FakeStore
) -> None:
    await proc.handle(commit(LISTENER_NSID, "create", "l1", listener_record(), did=OTHER))
    other_coll = f"at://{DID}/app.bsky.feed.post/x"
    await proc.handle(commit(LISTENER_NSID, "create", "l2", listener_record(other_coll)))
    await proc.handle(commit(LISTENER_NSID, "create", "l3", {"subject": EV_URI}))
    assert store.listeners == {}


async def test_listener_delete_and_change_callback(
    store: FakeStore, notifier: FakeNotifier
) -> None:
    seen: list[list[str]] = []
    proc = CommitProcessor(store, notifier, on_listeners_changed=seen.append, clock=lambda: NOW)
    await proc.handle(commit(LISTENER_NSID, "create", "l1", listener_record()))
    await proc.handle(commit(LISTENER_NSID, "create", "l2", listener_record(hashtag="tacos")))
    await proc.handle(commit(LISTENER_NSID, "delete", "l1"))
    await proc.handle(commit(LISTENER_NSID, "delete", "l2"))
    assert store.listeners == {}
    assert seen == [[DID], []]  # only fired when the DID set changed


async def test_async_listener_callback_awaited(store: FakeStore, notifier: FakeNotifier) -> None:
    seen: list[list[str]] = []

    async def cb(dids: list[str]) -> None:
        seen.append(dids)

    proc = CommitProcessor(store, notifier, on_listeners_changed=cb)
    await proc.handle(commit(LISTENER_NSID, "create", "l1", listener_record()))
    assert seen == [[DID]]


# ---- posts ----------------------------------------------------------------


def post(text: str, facets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rec: dict[str, Any] = {"$type": POST_NSID, "text": text, "createdAt": "2026-11-11T12:00:00Z"}
    if facets is not None:
        rec["facets"] = facets
    return rec


async def _with_listener(proc: CommitProcessor) -> None:
    await proc.handle(commit(EVENT_NSID, "create", "ev1", event_record()))
    await proc.handle(commit(LISTENER_NSID, "create", "l1", listener_record()))


async def test_post_with_hashtag_becomes_announcement(
    proc: CommitProcessor, store: FakeStore, notifier: FakeNotifier
) -> None:
    await _with_listener(proc)
    text = "Moved inside due to rain! #tacoNIGHT"
    await proc.handle(commit(POST_NSID, "create", "p1", post(text)))
    (upd,) = store.list_updates(EV_URI)
    assert upd.text == text
    assert upd.source_uri == f"at://{DID}/{POST_NSID}/p1"
    assert upd.created_at == NOW
    assert notifier.published == [(EV_URI, "announcement", text)]


async def test_post_hashtag_from_facet(proc: CommitProcessor, store: FakeStore) -> None:
    await _with_listener(proc)
    facet = {"features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "TacoNight"}]}
    await proc.handle(commit(POST_NSID, "create", "p1", post("see you there", [facet])))
    assert len(store.list_updates(EV_URI)) == 1


async def test_post_partial_or_missing_tag_ignored(
    proc: CommitProcessor, store: FakeStore, notifier: FakeNotifier
) -> None:
    await _with_listener(proc)
    await proc.handle(commit(POST_NSID, "create", "p1", post("#TacoNightOut is fun")))
    await proc.handle(commit(POST_NSID, "create", "p2", post("taconight without hash")))
    await proc.handle(commit(POST_NSID, "create", "p3", post("#taconight"), did=OTHER))
    await proc.handle(commit(POST_NSID, "delete", "p1"))
    assert store.updates == []
    assert [p for p in notifier.published if p[1] == "announcement"] == []


def test_extract_hashtags() -> None:
    rec = post("Hi #One, #two! mid#no #thr-ee.")
    assert extract_hashtags(rec) == {"one", "two", "thr-ee"}
