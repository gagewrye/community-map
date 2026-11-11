from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from app.ingest.jetstream import (
    Backoff,
    CursorSaver,
    JetstreamClient,
    parse_message,
    resume_cursor,
)
from app.ingest.processor import CommitProcessor
from app.models import EVENT_NSID, LISTENER_NSID, POST_NSID
from tests.ingest_fakes import FakeNotifier, FakeStore

BASE = "wss://js.example/subscribe"
DID = "did:plc:alice"


class FakeConnect:
    """Each call pops a script: a list of raw messages, or an Exception to raise on connect."""

    def __init__(self, scripts: list[list[str] | Exception]) -> None:
        self.scripts = scripts
        self.urls: list[str] = []

    def __call__(self, url: str) -> Any:
        self.urls.append(url)
        script = self.scripts.pop(0) if self.scripts else []

        @asynccontextmanager
        async def cm() -> AsyncIterator[AsyncIterator[str]]:
            if isinstance(script, Exception):
                raise script

            async def gen() -> AsyncIterator[str]:
                for m in script:
                    yield m

            yield gen()

        return cm()


class StopAfter:
    """Fake sleep: records delays, cancels the loop after n sleeps."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)  # yield like a real sleep
        if len(self.delays) >= self.n:
            raise asyncio.CancelledError


def make_client(
    connect: FakeConnect, sleep: StopAfter | None = None
) -> tuple[JetstreamClient, FakeStore]:
    store = FakeStore()
    proc = CommitProcessor(store, FakeNotifier(store))
    client = JetstreamClient(BASE, proc, store, connect=connect, sleep=sleep or StopAfter(1))
    return client, store


def event_msg(rkey: str, time_us: int) -> str:
    record = {
        "name": "Taco Night",
        "startsAt": "2026-11-12T18:00:00Z",
        "endsAt": "2026-11-12T20:00:00Z",
        "location": {"name": "Price Center"},
        "createdAt": "2026-11-11T00:00:00Z",
    }
    commit = {"operation": "create", "collection": EVENT_NSID, "rkey": rkey, "record": record}
    return json.dumps({"did": DID, "time_us": time_us, "kind": "commit", "commit": commit})


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


# ---- pure helpers -----------------------------------------------------------


def test_build_url() -> None:
    client, _ = make_client(FakeConnect([]))
    url = client.build_url([EVENT_NSID, LISTENER_NSID], ["did:plc:a", "did:plc:b"], 123)
    assert url.startswith(BASE + "?")
    q = query(url)
    assert q["wantedCollections"] == [EVENT_NSID, LISTENER_NSID]
    assert q["wantedDids"] == ["did:plc:a", "did:plc:b"]
    assert q["cursor"] == ["123"]
    assert client.build_url([], [], None) == BASE


def test_parse_message() -> None:
    assert parse_message('{"kind":"commit"}') == {"kind": "commit"}
    assert parse_message(b'{"a":1}') == {"a": 1}
    assert parse_message("not json") is None
    assert parse_message("[1,2]") is None


def test_resume_cursor_rewinds_five_seconds() -> None:
    assert resume_cursor(None) is None
    assert resume_cursor(10_000_000) == 5_000_000
    assert resume_cursor(1) == 0


def test_backoff_doubles_and_caps() -> None:
    b = Backoff()
    assert [b.next() for _ in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]
    b.reset()
    assert b.next() == 1


def test_cursor_saver_every_n_and_interval() -> None:
    store = FakeStore()
    now = [0.0]
    saver = CursorSaver(store, "js", every=3, interval_s=5, clock=lambda: now[0])
    saver.seen(10)
    saver.seen(20)
    assert store.get_cursor("js") is None
    saver.seen(30)
    assert store.get_cursor("js") == 30
    saver.seen(40)
    now[0] = 6.0
    saver.seen(35)  # out-of-order time_us never moves the cursor backwards
    assert store.get_cursor("js") == 40
    saver.seen("bogus")
    saver.flush()
    assert store.get_cursor("js") == 40


# ---- connection behaviour ---------------------------------------------------


async def test_consume_processes_and_saves_cursor() -> None:
    connect = FakeConnect([[event_msg("a", 100), "garbage", event_msg("b", 200)]])
    client, store = make_client(connect)
    n = await client.consume_once("js", [EVENT_NSID], [])
    assert n == 3
    assert len(store.events) == 2
    assert store.get_cursor("js") == 200
    assert "cursor" not in query(connect.urls[0])


async def test_consume_resumes_from_rewound_cursor() -> None:
    connect = FakeConnect([[]])
    client, store = make_client(connect)
    store.set_cursor("js", 20_000_000)
    await client.consume_once("js", [EVENT_NSID], [])
    assert query(connect.urls[0])["cursor"] == ["15000000"]


async def test_processor_errors_do_not_drop_connection() -> None:
    connect = FakeConnect([[event_msg("a", 100), event_msg("b", 200)]])
    client, store = make_client(connect)

    async def boom(msg: dict[str, Any]) -> None:
        raise RuntimeError("db down")

    client.processor.handle = boom  # type: ignore[method-assign]
    assert await client.consume_once("js", [EVENT_NSID], []) == 2
    assert store.get_cursor("js") == 200


async def test_run_stream_reconnects_with_backoff() -> None:
    connect = FakeConnect([OSError("refused"), OSError("refused"), [event_msg("a", 1)], []])
    sleep = StopAfter(4)
    client, store = make_client(connect, sleep)
    with pytest.raises(asyncio.CancelledError):
        await client.run_stream("js", [EVENT_NSID], [])
    # fail, fail, success (resets), empty connection (no reset)
    assert sleep.delays == [1, 2, 1, 2]
    assert len(store.events) == 1


async def test_posts_stream_only_with_listener_dids() -> None:
    connect = FakeConnect([])
    client, store = make_client(connect, StopAfter(10**9))
    task = asyncio.create_task(client.run_forever())
    await asyncio.sleep(0.01)
    urls = list(connect.urls)
    assert urls and all(POST_NSID not in u for u in urls)

    listener = {
        "subject": f"at://{DID}/{EVENT_NSID}/ev1",
        "hashtag": "tacos",
        "createdAt": "2026-11-11T00:00:00Z",
    }
    commit = {"operation": "create", "collection": LISTENER_NSID, "rkey": "l1", "record": listener}
    await client.processor.handle({"did": DID, "kind": "commit", "commit": commit})
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    post_urls = [u for u in connect.urls if POST_NSID in u]
    assert post_urls
    assert all(query(u)["wantedDids"] == [DID] for u in post_urls)
    assert all(query(u)["wantedCollections"] == [POST_NSID] for u in post_urls)
