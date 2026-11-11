"""Jetstream (JSON firehose) client: feeds commit messages to a CommitProcessor.

Two connections:
  * "events": wantedCollections = event + listener NSIDs, all DIDs.
  * "posts":  wantedCollections = app.bsky.feed.post, wantedDids = store.listener_dids().
    Only runs while there are listeners and is restarted when that set changes; we never
    subscribe to the full Bluesky post stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any
from urllib.parse import urlencode

import websockets

from app.ingest.processor import CommitProcessor
from app.models import EVENT_NSID, LISTENER_NSID, POST_NSID
from app.store.base import EventStore

log = logging.getLogger(__name__)

REWIND_US = 5_000_000  # replay the last 5s on resume; processing is idempotent
MAX_WANTED_DIDS = 10_000  # Jetstream's limit
Connect = Callable[[str], AbstractAsyncContextManager[AsyncIterator[str | bytes]]]
Sleep = Callable[[float], Awaitable[None]]


def parse_message(raw: str | bytes) -> dict[str, Any] | None:
    try:
        msg = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return msg if isinstance(msg, dict) else None


def resume_cursor(stored: int | None) -> int | None:
    return None if stored is None else max(stored - REWIND_US, 0)


class Backoff:
    """Exponential backoff: 1s, 2s, 4s ... capped at 60s."""

    def __init__(self, initial: float = 1.0, cap: float = 60.0) -> None:
        self.initial, self.cap = initial, cap
        self.current = initial

    def next(self) -> float:
        delay = self.current
        self.current = min(self.current * 2, self.cap)
        return delay

    def reset(self) -> None:
        self.current = self.initial


class CursorSaver:
    """Tracks the latest time_us and persists it every `every` messages or `interval_s`."""

    def __init__(
        self,
        store: EventStore,
        name: str,
        every: int = 100,
        interval_s: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store, self.name = store, name
        self.every, self.interval_s, self.clock = every, interval_s, clock
        self.latest: int | None = None
        self._pending = 0
        self._last_save = clock()

    def seen(self, time_us: Any) -> None:
        if not isinstance(time_us, int):
            return
        self.latest = max(time_us, self.latest or 0)
        self._pending += 1
        if self._pending >= self.every or self.clock() - self._last_save >= self.interval_s:
            self.flush()

    def flush(self) -> None:
        if self.latest is not None and self._pending:
            self.store.set_cursor(self.name, self.latest)
        self._pending = 0
        self._last_save = self.clock()


class JetstreamClient:
    """Note: installs itself as processor.on_listeners_changed to restart the posts stream."""

    def __init__(
        self,
        url: str,
        processor: CommitProcessor,
        store: EventStore,
        cursor_name: str = "jetstream",
        connect: Connect = websockets.connect,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.url = url
        self.processor = processor
        self.store = store
        self.cursor_name = cursor_name
        self.connect = connect
        self.sleep = sleep
        self._dids_changed = asyncio.Event()
        processor.on_listeners_changed = self.listeners_changed

    def build_url(self, collections: list[str], dids: list[str], cursor: int | None) -> str:
        params: list[tuple[str, str]] = [("wantedCollections", c) for c in collections]
        params += [("wantedDids", d) for d in dids]
        if cursor is not None:
            params.append(("cursor", str(cursor)))
        sep = "&" if "?" in self.url else "?"
        return f"{self.url}{sep}{urlencode(params)}" if params else self.url

    def listeners_changed(self, dids: list[str]) -> None:
        self._dids_changed.set()

    async def run_forever(self) -> None:
        await asyncio.gather(
            self.run_stream(self.cursor_name, [EVENT_NSID, LISTENER_NSID], []),
            self._run_posts(),
        )

    async def run_stream(self, name: str, collections: list[str], dids: list[str]) -> None:
        """Consume one subscription forever, reconnecting with backoff."""
        backoff = Backoff()
        while True:
            try:
                if await self.consume_once(name, collections, dids):
                    backoff.reset()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # network errors, bad handshakes, ...
                log.warning("jetstream %s disconnected: %r", name, e)
            await self.sleep(backoff.next())

    async def consume_once(self, name: str, collections: list[str], dids: list[str]) -> int:
        """One connection: resume from stored cursor, process until closed. Returns msg count."""
        saver = CursorSaver(self.store, name)
        url = self.build_url(collections, dids, resume_cursor(self.store.get_cursor(name)))
        count = 0
        try:
            async with self.connect(url) as ws:
                log.info("jetstream %s connected", name)
                async for raw in ws:
                    count += 1
                    await self._process(raw, saver)
        finally:
            saver.flush()
        return count

    async def _process(self, raw: str | bytes, saver: CursorSaver) -> None:
        msg = parse_message(raw)
        if msg is None:
            return
        try:
            await self.processor.handle(msg)
        except Exception:
            log.exception("failed to process jetstream message")
        saver.seen(msg.get("time_us"))

    async def _run_posts(self) -> None:
        name = f"{self.cursor_name}:posts"
        while True:
            self._dids_changed.clear()
            dids = self.store.listener_dids()[:MAX_WANTED_DIDS]
            task = None
            if dids:
                task = asyncio.create_task(self.run_stream(name, [POST_NSID], dids))
            try:
                await self._dids_changed.wait()
            finally:
                if task is not None:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
