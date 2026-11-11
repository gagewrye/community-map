"""Turns Jetstream commit messages into index changes and notifications.

Network-free: everything external (store, notifier, handle lookup, clock) is injected.
"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from app.models import (
    EVENT_NSID,
    LISTENER_NSID,
    POST_NSID,
    EventRecord,
    EventUpdate,
    IndexedEvent,
    Listener,
    ListenerRecord,
)
from app.notify.base import Notifier
from app.store.base import EventStore, UpsertResult

log = logging.getLogger(__name__)

TAG_FACET = "app.bsky.richtext.facet#tag"
_HASHTAG = re.compile(r"(?<![\w#])#([^\s#]+)")
_TRAILING_PUNCT = ".,;:!?)]}\"'"

ListenersChanged = Callable[[list[str]], None | Awaitable[None]]


class HandleLookup(Protocol):
    async def resolve(self, did: str) -> str | None: ...


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Commit:
    did: str
    operation: str
    collection: str
    rkey: str
    cid: str | None
    record: dict[str, Any] | None

    @property
    def uri(self) -> str:
        return f"at://{self.did}/{self.collection}/{self.rkey}"


def parse_commit(msg: dict[str, Any]) -> Commit | None:
    """Extract the commit from a Jetstream message, or None if it is not a usable commit."""
    body = msg.get("commit")
    if msg.get("kind") != "commit" or not isinstance(body, dict):
        return None
    did, op = msg.get("did"), body.get("operation")
    coll, rkey = body.get("collection"), body.get("rkey")
    if not all(isinstance(v, str) and v for v in (did, op, coll, rkey)):
        return None
    record = body.get("record")
    return Commit(
        did, op, coll, rkey, body.get("cid"), record if isinstance(record, dict) else None
    )


# ---- diffs ------------------------------------------------------------------


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%a %b %d %H:%M UTC")


def _fmt_list(items: list[str]) -> str:
    return ", ".join(items) or "none"


def diff_events(old: EventRecord, new: EventRecord) -> list[str]:
    """Human-readable list of what changed between two versions of an event."""
    out: list[str] = []
    if old.name != new.name:
        out.append(f"Name changed: {old.name} → {new.name}")
    if old.starts_at != new.starts_at:
        out.append(f"Time changed: {_fmt_time(old.starts_at)} → {_fmt_time(new.starts_at)}")
    elif old.ends_at != new.ends_at:
        out.append(f"End time changed: {_fmt_time(old.ends_at)} → {_fmt_time(new.ends_at)}")
    if old.location.name != new.location.name:
        out.append(f"Location changed: {old.location.name} → {new.location.name}")
    elif old.location != new.location:
        out.append("Location details updated")
    if old.description != new.description:
        out.append("Description updated")
    if old.tags != new.tags:
        out.append(f"Tags changed: {_fmt_list(old.tags)} → {_fmt_list(new.tags)}")
    if old.group != new.group:
        out.append(f"Group changed: {old.group or 'none'} → {new.group or 'none'}")
    return out


async def index_event(
    store: EventStore, notifier: Notifier, ev: IndexedEvent, existing: IndexedEvent | None
) -> UpsertResult:
    """Upsert ev (keeping existing.indexed_at) and notify subscribers of meaningful changes."""
    if existing is not None:
        ev = ev.model_copy(update={"indexed_at": existing.indexed_at})
    result = store.upsert_event(ev)
    if result == "updated" and existing is not None:
        diffs = diff_events(existing.record, ev.record)
        if diffs:
            await notifier.publish(ev.uri, "updated", "; ".join(diffs))
    return result


# ---- hashtags ---------------------------------------------------------------


def extract_hashtags(post: dict[str, Any]) -> set[str]:
    """Lower-cased hashtags from a post's text and its richtext tag facets."""
    text = post.get("text")
    tags = set()
    if isinstance(text, str):
        tags = {m.rstrip(_TRAILING_PUNCT).lower() for m in _HASHTAG.findall(text)}
    for facet in post.get("facets") or []:
        for feat in facet.get("features", []) if isinstance(facet, dict) else []:
            if isinstance(feat, dict) and feat.get("$type") == TAG_FACET:
                tag = feat.get("tag")
                if isinstance(tag, str):
                    tags.add(tag.lstrip("#").lower())
    tags.discard("")
    return tags


# ---- processor --------------------------------------------------------------


class CommitProcessor:
    def __init__(
        self,
        store: EventStore,
        notifier: Notifier,
        handle_resolver: HandleLookup | None = None,
        on_listeners_changed: ListenersChanged | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.store = store
        self.notifier = notifier
        self.handle_resolver = handle_resolver
        self.on_listeners_changed = on_listeners_changed
        self.clock = clock

    async def handle(self, msg: dict[str, Any]) -> None:
        c = parse_commit(msg)
        if c is None:
            return
        if c.collection == EVENT_NSID:
            await self._event(c)
        elif c.collection == LISTENER_NSID:
            await self._listener(c)
        elif c.collection == POST_NSID and c.operation == "create":
            await self._post(c)

    # events

    async def _event(self, c: Commit) -> None:
        if c.operation == "delete":
            await self._delete_event(c.uri)
            return
        try:
            record = EventRecord.model_validate(c.record or {})
        except ValidationError as e:
            log.info("skipping invalid event %s: %s", c.uri, e.errors()[:3])
            return
        existing = self.store.get_event(c.uri)
        now = self.clock()
        ev = IndexedEvent(
            uri=c.uri,
            cid=c.cid,
            author_did=c.did,
            author_handle=await self._handle(c.did, existing),
            source="atproto",
            record=record,
            indexed_at=now,
            updated_at=now,
        )
        await index_event(self.store, self.notifier, ev, existing)

    async def _delete_event(self, uri: str) -> None:
        existing = self.store.get_event(uri)
        if existing is None:
            return
        # Publish first: the notifier looks up subscribers of this event.
        await self.notifier.publish(uri, "deleted", f"{existing.record.name} was cancelled")
        self.store.delete_event(uri)

    async def _handle(self, did: str, existing: IndexedEvent | None) -> str | None:
        if existing is not None and existing.author_handle:
            return existing.author_handle
        if self.handle_resolver is None:
            return None
        return await self.handle_resolver.resolve(did)

    # listeners

    async def _listener(self, c: Commit) -> None:
        before = self.store.listener_dids()
        if c.operation == "delete":
            self.store.delete_listener(c.uri)
        else:
            listener = self._parse_listener(c)
            if listener is None:
                return
            self.store.upsert_listener(listener)
        after = self.store.listener_dids()
        if after != before and self.on_listeners_changed is not None:
            res = self.on_listeners_changed(after)
            if inspect.isawaitable(res):
                await res

    def _parse_listener(self, c: Commit) -> Listener | None:
        try:
            record = ListenerRecord.model_validate(c.record or {})
        except ValidationError as e:
            log.info("skipping invalid listener %s: %s", c.uri, e.errors()[:3])
            return None
        if not record.subject.startswith(f"at://{c.did}/{EVENT_NSID}/"):
            log.info("rejecting listener %s: subject %s not owned by author", c.uri, record.subject)
            return None
        return Listener(uri=c.uri, author_did=c.did, record=record)

    # posts

    async def _post(self, c: Commit) -> None:
        listeners = self.store.listeners_for_did(c.did)
        if not listeners or c.record is None:
            return
        tags = extract_hashtags(c.record)
        subjects = {li.record.subject for li in listeners if li.record.hashtag in tags}
        text = c.record.get("text") or ""
        for subject in sorted(subjects):
            upd = EventUpdate(
                event_uri=subject, text=text, source_uri=c.uri, created_at=self.clock()
            )
            self.store.add_update(upd)
            await self.notifier.publish(subject, "announcement", text)
