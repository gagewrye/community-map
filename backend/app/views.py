"""JSON views returned by the HTTP API (see docs/CONTRACTS.md, EventView)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.models import EventUpdate, IndexedEvent

ENDING_SOON = timedelta(hours=1)

Status = Literal["upcoming", "live", "ending_soon"]


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def event_status(ev: IndexedEvent, now: datetime) -> Status:
    now = _utc(now)
    if now < _utc(ev.record.starts_at):
        return "upcoming"
    if _utc(ev.record.ends_at) - now <= ENDING_SOON:
        return "ending_soon"
    return "live"


def event_view(ev: IndexedEvent, now: datetime) -> dict[str, Any]:
    record = ev.record.model_dump(mode="json", by_alias=True)
    meta = ev.model_dump(mode="json", by_alias=True, exclude={"record"})
    return {**meta, **record, "status": event_status(ev, now)}


def update_view(upd: EventUpdate) -> dict[str, Any]:
    return upd.model_dump(mode="json", by_alias=True, include={"text", "source_uri", "created_at"})
