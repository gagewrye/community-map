from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import events, meta, subscriptions
from app.config import Settings
from app.models import EVENT_NSID, EventRecord, IndexedEvent, Location
from app.notify.service import SubscriptionNotifier
from app.store.sqlite import SqliteStore

MakeEvent = Callable[..., IndexedEvent]


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@pytest.fixture
def store() -> Iterator[SqliteStore]:
    s = SqliteStore(":memory:")
    yield s
    s.close()


@pytest.fixture
def notifier(store: SqliteStore) -> SubscriptionNotifier:
    return SubscriptionNotifier(store)


@pytest.fixture
def make_event(now: datetime) -> MakeEvent:
    """Build an IndexedEvent; times are hour offsets from `now`."""

    def _make(
        rkey: str = "e1",
        *,
        name: str = "Test Event",
        start_h: float = 1,
        end_h: float = 2,
        tags: list[str] | None = None,
        group: str | None = None,
        description: str = "",
        location: str = "Price Center",
        cid: str | None = "bafy1",
        did: str = "did:plc:test",
        **extra: Any,
    ) -> IndexedEvent:
        record = EventRecord(
            name=name,
            description=description,
            starts_at=now + timedelta(hours=start_h),
            ends_at=now + timedelta(hours=end_h),
            location=Location(name=location, lat="32.8797", lng="-117.2362"),
            tags=tags or [],
            group=group,
            created_at=now,
        )
        fields: dict[str, Any] = {"indexed_at": now, "updated_at": now, **extra}
        return IndexedEvent(
            uri=f"at://{did}/{EVENT_NSID}/{rkey}",
            cid=cid,
            author_did=did,
            record=record,
            **fields,
        )

    return _make


@pytest.fixture
def settings() -> Settings:
    return Settings(db_path=":memory:", dev_mode=True, jetstream_enabled=False)


@pytest.fixture
def app(store: SqliteStore, notifier: SubscriptionNotifier, settings: Settings) -> FastAPI:
    app = FastAPI()
    for module in (meta, events, subscriptions):
        app.include_router(module.router)
    app.state.store = store
    app.state.notifier = notifier
    app.state.settings = settings
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
