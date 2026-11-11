"""In-memory fakes of the EventStore / Notifier Protocols used by the ingest tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import EventUpdate, IndexedEvent, Listener, NotificationKind
from app.store.base import UpsertResult


class FakeStore:
    def __init__(self) -> None:
        self.events: dict[str, IndexedEvent] = {}
        self.updates: list[EventUpdate] = []
        self.listeners: dict[str, Listener] = {}
        self.cursors: dict[str, int] = {}

    # events
    def upsert_event(self, ev: IndexedEvent) -> UpsertResult:
        old = self.events.get(ev.uri)
        if old is not None and _same(old, ev):
            return "unchanged"
        self.events[ev.uri] = ev
        return "created" if old is None else "updated"

    def get_event(self, uri: str) -> IndexedEvent | None:
        return self.events.get(uri)

    def delete_event(self, uri: str) -> bool:
        return self.events.pop(uri, None) is not None

    # updates
    def add_update(self, upd: EventUpdate) -> None:
        self.updates.append(upd)

    def list_updates(self, event_uri: str) -> list[EventUpdate]:
        return [u for u in self.updates if u.event_uri == event_uri]

    # listeners
    def upsert_listener(self, listener: Listener) -> None:
        self.listeners[listener.uri] = listener

    def delete_listener(self, uri: str) -> bool:
        return self.listeners.pop(uri, None) is not None

    def listeners_for_did(self, did: str) -> list[Listener]:
        return [li for li in self.listeners.values() if li.author_did == did]

    def listener_dids(self) -> list[str]:
        return sorted({li.author_did for li in self.listeners.values()})

    # cursors
    def get_cursor(self, name: str) -> int | None:
        return self.cursors.get(name)

    def set_cursor(self, name: str, value: int) -> None:
        self.cursors[name] = value


def _same(a: IndexedEvent, b: IndexedEvent) -> bool:
    return (a.record, a.cid, a.author_handle) == (b.record, b.cid, b.author_handle)


class FakeNotifier:
    """Records publish calls; with a store, also records whether the event still existed."""

    def __init__(self, store: FakeStore | None = None) -> None:
        self.store = store
        self.published: list[tuple[str, NotificationKind, str]] = []
        self.event_present: list[bool] = []

    async def publish(self, event_uri: str, kind: NotificationKind, message: str) -> int:
        self.published.append((event_uri, kind, message))
        if self.store is not None:
            self.event_present.append(self.store.get_event(event_uri) is not None)
        return 1


class FakeResolver:
    def __init__(self, handles: dict[str, str]) -> None:
        self.handles = handles
        self.calls: list[str] = []

    async def resolve(self, did: str) -> str | None:
        self.calls.append(did)
        return self.handles.get(did)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)
