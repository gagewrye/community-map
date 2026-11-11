"""Import events from iCalendar (.ics) feeds into the index."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from icalendar import Calendar, Component
from pydantic import ValidationError

from app.config import Settings
from app.ingest.processor import index_event, utcnow
from app.models import EventRecord, IndexedEvent, Location
from app.notify.base import Notifier
from app.store.base import EventStore

log = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 10.0
DEFAULT_DURATION = timedelta(hours=1)
NO_LOCATION = "TBA"


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def event_uri(feed_url: str, uid: str) -> str:
    return f"ical://{_sha1(feed_url)[:12]}/{_sha1(uid)[:16]}"


def _to_utc(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)  # all-day


def _window(ve: Component) -> tuple[datetime, datetime]:
    raw_start = ve["DTSTART"].dt
    start = _to_utc(raw_start)
    if "DTEND" in ve:
        end = _to_utc(ve["DTEND"].dt)
    elif "DURATION" in ve:
        end = start + ve["DURATION"].dt
    elif isinstance(raw_start, datetime):
        end = start + DEFAULT_DURATION
    else:
        end = start + timedelta(days=1)  # all-day event without DTEND
    return start, end


def _text(ve: Component, key: str, limit: int) -> str | None:
    value = ve.get(key)
    if value is None:
        return None
    return str(value).strip()[:limit] or None


def _location(ve: Component) -> Location:
    name = _text(ve, "LOCATION", 200) or NO_LOCATION
    geo = ve.get("GEO")
    if geo is None:
        return Location(name=name)
    return Location(name=name, lat=str(geo.latitude), lng=str(geo.longitude))


def _record(ve: Component, now: datetime) -> EventRecord:
    start, end = _window(ve)
    created = ve.get("CREATED")
    return EventRecord(
        name=_text(ve, "SUMMARY", 200) or "",
        description=_text(ve, "DESCRIPTION", 3000) or "",
        starts_at=start,
        ends_at=end,
        location=_location(ve),
        tags=[str(c) for c in ve.categories][:10],
        source_url=_text(ve, "URL", 2000),
        created_at=_to_utc(created.dt) if created is not None else now,
    )


def _event(ve: Component, feed_url: str, author: str, now: datetime) -> IndexedEvent | None:
    uid = _text(ve, "UID", 1000)
    if uid is None:
        raise ValueError("VEVENT without UID")
    record = _record(ve, now)
    if record.ends_at < now:
        return None
    return IndexedEvent(
        uri=event_uri(feed_url, uid),
        author_did=author,
        source="ical",
        record=record,
        indexed_at=now,
        updated_at=now,
    )


def parse_ics(text: str, feed_url: str, now: datetime) -> list[IndexedEvent]:
    """Parse a feed into IndexedEvents. Raises ValueError if text is not a calendar at all."""
    cal = Calendar.from_ical(text)
    author = "ical:" + (urlsplit(feed_url).hostname or "unknown")
    out: list[IndexedEvent] = []
    for ve in cal.walk("VEVENT"):
        try:
            ev = _event(ve, feed_url, author, now)
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError) as e:
            log.info("skipping malformed VEVENT in %s: %s", feed_url, e)
            continue
        if ev is not None:
            out.append(ev)
    return out


async def import_feed(
    url: str, store: EventStore, notifier: Notifier, client: httpx.AsyncClient
) -> int:
    """Fetch and index one feed; returns the number of (current) events imported.

    Raises httpx.HTTPError on fetch failure, ValueError if the body is not iCalendar.
    """
    resp = await client.get(url, timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    events = parse_ics(resp.text, url, utcnow())
    for ev in events:
        existing = store.get_event(ev.uri)
        if existing is not None:  # feeds rarely carry CREATED; keep ours stable
            record = ev.record.model_copy(update={"created_at": existing.record.created_at})
            ev = ev.model_copy(update={"record": record})
        await index_event(store, notifier, ev, existing)
    return len(events)


def feed_urls(settings: Settings) -> list[str]:
    return [u.strip() for u in settings.ical_feeds.split(",") if u.strip()]


async def run_ical_loop(
    store: EventStore,
    notifier: Notifier,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Poll every configured feed forever; individual feed failures are logged and skipped."""
    urls = feed_urls(settings)
    if not urls:
        return
    http = client or httpx.AsyncClient()
    try:
        while True:
            for url in urls:
                await _import_logged(url, store, notifier, http)
            await sleep(settings.ical_interval_s)
    finally:
        if client is None:
            await http.aclose()


async def _import_logged(
    url: str, store: EventStore, notifier: Notifier, client: httpx.AsyncClient
) -> None:
    try:
        n = await import_feed(url, store, notifier, client)
        log.info("imported %d events from %s", n, url)
    except Exception as e:  # keep polling other feeds / next round
        log.warning("ical import failed for %s: %r", url, e)
