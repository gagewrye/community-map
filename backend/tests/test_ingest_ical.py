from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest

from app.config import Settings
from app.ingest.ical import event_uri, import_feed, parse_ics, run_ical_loop
from tests.ingest_fakes import FakeNotifier, FakeStore, utc

FEED = "https://calendar.example.edu/events.ics"
NOW = utc(2026, 11, 11, 12)


def vevent(*lines: str) -> str:
    return "BEGIN:VEVENT\n" + "\n".join(lines) + "\nEND:VEVENT\n"


def calendar(*events: str) -> str:
    return (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\n" + "".join(events) + "END:VCALENDAR\n"
    )


TACO = vevent(
    "UID:taco@example.edu",
    "SUMMARY:Taco Night",
    "DESCRIPTION:Free tacos",
    "DTSTART:20261112T180000Z",
    "DTEND:20261112T200000Z",
    "LOCATION:Price Center",
    "GEO:32.88;-117.24",
    "CATEGORIES:Food,Free",
    "URL:https://example.edu/taco",
)


def test_parse_full_event() -> None:
    (ev,) = parse_ics(calendar(TACO), FEED, NOW)
    assert ev.uri == event_uri(FEED, "taco@example.edu")
    assert ev.uri.startswith("ical://") and len(ev.uri.split("/")[-1]) == 16
    assert ev.author_did == "ical:calendar.example.edu"
    assert ev.source == "ical"
    r = ev.record
    assert r.name == "Taco Night" and r.description == "Free tacos"
    assert r.starts_at == utc(2026, 11, 12, 18) and r.ends_at == utc(2026, 11, 12, 20)
    assert r.location.name == "Price Center"
    assert (r.location.lat, r.location.lng) == ("32.88", "-117.24")
    assert r.tags == ["food", "free"]
    assert r.source_url == "https://example.edu/taco"
    assert r.created_at == NOW


def test_missing_dtend_and_all_day_and_tz() -> None:
    text = calendar(
        vevent("UID:a", "SUMMARY:No end", "DTSTART:20261112T180000Z"),
        vevent("UID:b", "SUMMARY:All day", "DTSTART;VALUE=DATE:20261113"),
        vevent(
            "UID:c",
            "SUMMARY:Pacific",
            "DTSTART;TZID=America/Los_Angeles:20261112T100000",
            "DURATION:PT30M",
        ),
    )
    a, b, c = parse_ics(text, FEED, NOW)
    assert a.record.ends_at - a.record.starts_at == timedelta(hours=1)
    assert a.record.location.name == "TBA"
    assert b.record.starts_at == utc(2026, 11, 13)
    assert b.record.ends_at == utc(2026, 11, 14)
    assert c.record.starts_at == utc(2026, 11, 12, 18)
    assert c.record.ends_at == utc(2026, 11, 12, 18, 30)


def test_skips_ended_and_malformed() -> None:
    text = calendar(
        vevent("UID:old", "SUMMARY:Past", "DTSTART:20261101T180000Z", "DTEND:20261101T190000Z"),
        vevent("UID:bad", "SUMMARY:Broken", "DTSTART:garbage"),
        vevent("SUMMARY:No uid", "DTSTART:20261112T180000Z"),
        vevent("UID:noname", "DTSTART:20261112T180000Z"),
        vevent("UID:nostart", "SUMMARY:x"),
        TACO,
    )
    assert [e.record.name for e in parse_ics(text, FEED, NOW)] == ["Taco Night"]


def test_not_a_calendar_raises() -> None:
    with pytest.raises(ValueError):
        parse_ics("<html>nope</html>", FEED, NOW)


def mock_client(bodies: list[str], status: int = 200) -> httpx.AsyncClient:
    def handle(req: httpx.Request) -> httpx.Response:
        body = bodies.pop(0) if len(bodies) > 1 else bodies[0]
        return httpx.Response(status, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


async def test_import_feed_upserts_and_notifies_changes() -> None:
    store = FakeStore()
    notifier = FakeNotifier(store)
    moved = TACO.replace("LOCATION:Price Center", "LOCATION:Sun God Lawn")
    client = mock_client([calendar(TACO), calendar(TACO), calendar(moved)])

    assert await import_feed(FEED, store, notifier, client) == 1
    (uri,) = store.events
    first = store.events[uri]
    assert await import_feed(FEED, store, notifier, client) == 1
    assert store.events[uri] is first  # re-import of identical feed is "unchanged"
    assert notifier.published == []
    await import_feed(FEED, store, notifier, client)
    assert notifier.published == [(uri, "updated", "Location changed: Price Center → Sun God Lawn")]
    assert store.events[uri].indexed_at == first.indexed_at


async def test_import_feed_http_error() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        await import_feed(FEED, FakeStore(), FakeNotifier(), mock_client(["x"], status=404))


async def test_run_ical_loop_survives_errors() -> None:
    calls: list[str] = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if "bad" in str(req.url):
            raise httpx.ConnectError("down")
        return httpx.Response(200, text=calendar(TACO))

    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)
        if len(sleeps) == 2:
            raise asyncio.CancelledError

    store = FakeStore()
    settings = Settings(ical_feeds=f"https://bad.example/x.ics, {FEED}", ical_interval_s=7)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with pytest.raises(asyncio.CancelledError):
        await run_ical_loop(store, FakeNotifier(), settings, client=client, sleep=sleep)
    assert len(calls) == 4 and sleeps == [7, 7]
    assert len(store.events) == 1


async def test_run_ical_loop_no_feeds_returns() -> None:
    await run_ical_loop(FakeStore(), FakeNotifier(), Settings(ical_feeds=""))
