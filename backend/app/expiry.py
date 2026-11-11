"""Periodic removal of ended events, notifying subscribers first."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.models import EventQuery, IndexedEvent
from app.notify.base import Notifier
from app.store.base import EventStore

log = logging.getLogger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _expired_events(store: EventStore, cutoff: datetime) -> list[IndexedEvent]:
    """All events with endsAt < cutoff, found via the Protocol's query_events."""
    out: list[IndexedEvent] = []
    q = EventQuery(starts_before=cutoff, ends_after=_EPOCH, limit=100)
    while True:
        page = store.query_events(q, cutoff)
        out += [ev for ev in page.events if _utc(ev.record.ends_at) < cutoff]
        if page.cursor is None:
            return out
        q = q.model_copy(update={"cursor": page.cursor})


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def sweep_once(
    store: EventStore, notifier: Notifier, now: datetime, grace_s: int
) -> list[str]:
    cutoff = _utc(now) - timedelta(seconds=grace_s)
    for ev in _expired_events(store, cutoff):
        await notifier.publish(ev.uri, "expired", f"{ev.record.name} has ended")
    removed = store.delete_expired(cutoff)
    if removed:
        log.info("expired %d event(s)", len(removed))
    return removed


async def run_expiry_loop(store: EventStore, notifier: Notifier, settings: Settings) -> None:
    while True:
        try:
            await sweep_once(store, notifier, datetime.now(UTC), settings.expiry_grace_s)
        except Exception:
            log.exception("expiry sweep failed")
        await asyncio.sleep(settings.expiry_interval_s)
