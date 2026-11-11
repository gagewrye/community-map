"""SQLite implementation of EventStore (stdlib sqlite3, single shared connection)."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from app.models import (
    Count,
    EventQuery,
    EventRecord,
    EventUpdate,
    IndexedEvent,
    Listener,
    ListenerRecord,
    Notification,
    Page,
)
from app.store.base import UpsertResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    uri TEXT PRIMARY KEY,
    cid TEXT,
    author_did TEXT NOT NULL,
    author_handle TEXT,
    source TEXT NOT NULL,
    record TEXT NOT NULL,
    search TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    grp TEXT,
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_order ON events (starts_at, uri);
CREATE INDEX IF NOT EXISTS events_ends ON events (ends_at);
CREATE INDEX IF NOT EXISTS events_grp ON events (grp);
CREATE INDEX IF NOT EXISTS events_author ON events (author_did);
CREATE TABLE IF NOT EXISTS event_tags (
    uri TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (uri, tag)
);
CREATE INDEX IF NOT EXISTS event_tags_tag ON event_tags (tag);
CREATE TABLE IF NOT EXISTS updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uri TEXT NOT NULL,
    text TEXT NOT NULL,
    source_uri TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS updates_event ON updates (event_uri);
CREATE TABLE IF NOT EXISTS listeners (
    uri TEXT PRIMARY KEY,
    author_did TEXT NOT NULL,
    record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS listeners_did ON listeners (author_did);
CREATE TABLE IF NOT EXISTS subscriptions (
    subscriber_id TEXT NOT NULL,
    event_uri TEXT NOT NULL,
    PRIMARY KEY (subscriber_id, event_uri)
);
CREATE INDEX IF NOT EXISTS subscriptions_event ON subscriptions (event_uri);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id TEXT NOT NULL,
    event_uri TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_sub ON notifications (subscriber_id, id);
CREATE TABLE IF NOT EXISTS cursors (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


def to_iso(dt: datetime) -> str:
    """Fixed-width UTC ISO string (lexicographic order == chronological). Naive = UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def encode_cursor(starts_at: str, uri: str) -> str:
    return base64.urlsafe_b64encode(f"{starts_at}|{uri}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Raises ValueError on a malformed cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValueError("invalid cursor") from e
    starts_at, sep, uri = raw.partition("|")
    if not sep or not uri:
        raise ValueError("invalid cursor")
    return to_iso(from_iso(starts_at)), uri


def _norm_tag(tag: str) -> str:
    return tag.strip().lstrip("#").lower()


def _search_text(rec: EventRecord) -> str:
    return "\n".join([rec.name, rec.description, rec.location.name]).lower()


def _record_json(rec: EventRecord) -> str:
    return rec.model_dump_json(by_alias=True)


class SqliteStore:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._conn:
            yield self._conn

    def _all(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    # events

    def upsert_event(self, ev: IndexedEvent) -> UpsertResult:
        rec = ev.record
        rec_json = _record_json(rec)
        with self._tx() as c:
            row = c.execute(
                "SELECT cid, record, indexed_at FROM events WHERE uri = ?", (ev.uri,)
            ).fetchone()
            if row is not None and row["cid"] == ev.cid and row["record"] == rec_json:
                return "unchanged"
            indexed_at = row["indexed_at"] if row is not None else to_iso(ev.indexed_at)
            c.execute(
                "INSERT OR REPLACE INTO events (uri, cid, author_did, author_handle, source,"
                " record, search, starts_at, ends_at, grp, indexed_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ev.uri,
                    ev.cid,
                    ev.author_did,
                    ev.author_handle,
                    ev.source,
                    rec_json,
                    _search_text(rec),
                    to_iso(rec.starts_at),
                    to_iso(rec.ends_at),
                    rec.group,
                    indexed_at,
                    to_iso(ev.updated_at),
                ),
            )
            c.execute("DELETE FROM event_tags WHERE uri = ?", (ev.uri,))
            c.executemany(
                "INSERT OR IGNORE INTO event_tags (uri, tag) VALUES (?, ?)",
                [(ev.uri, t) for t in rec.tags],
            )
        return "created" if row is None else "updated"

    def get_event(self, uri: str) -> IndexedEvent | None:
        row = self._one("SELECT * FROM events WHERE uri = ?", (uri,))
        return _row_to_event(row) if row is not None else None

    def delete_event(self, uri: str) -> bool:
        """Also drops tags, updates and subscriptions: publish "deleted" before calling."""
        with self._tx() as c:
            existed = c.execute("SELECT 1 FROM events WHERE uri = ?", (uri,)).fetchone()
            _purge(c, [uri])
        return existed is not None

    def query_events(self, q: EventQuery, now: datetime) -> Page:
        where = ["ends_at >= ?"]
        params: list[Any] = [to_iso(q.ends_after or now)]
        tags = [t for t in (_norm_tag(t) for t in q.tags) if t]
        if tags:
            marks = ",".join("?" * len(tags))
            where.append(
                f"EXISTS (SELECT 1 FROM event_tags t WHERE t.uri = e.uri AND t.tag IN ({marks}))"
            )
            params += tags
        if q.group:
            where.append("grp = ?")
            params.append(q.group)
        if q.text:
            where.append("instr(search, ?) > 0")
            params.append(q.text.lower())
        if q.starts_before:
            where.append("starts_at < ?")
            params.append(to_iso(q.starts_before))
        if q.cursor:
            after_start, after_uri = decode_cursor(q.cursor)
            where.append("(starts_at > ? OR (starts_at = ? AND uri > ?))")
            params += [after_start, after_start, after_uri]
        sql = f"SELECT * FROM events e WHERE {' AND '.join(where)} ORDER BY starts_at, uri LIMIT ?"
        rows = self._all(sql, [*params, q.limit + 1])
        more = len(rows) > q.limit
        rows = rows[: q.limit]
        cursor = encode_cursor(rows[-1]["starts_at"], rows[-1]["uri"]) if more else None
        return Page(events=[_row_to_event(r) for r in rows], cursor=cursor)

    def delete_expired(self, cutoff: datetime) -> list[str]:
        with self._tx() as c:
            uris = [
                r["uri"]
                for r in c.execute("SELECT uri FROM events WHERE ends_at < ?", (to_iso(cutoff),))
            ]
            _purge(c, uris)
        return uris

    def list_tags(self, now: datetime) -> list[Count]:
        return self._counts(
            "SELECT t.tag AS value, COUNT(*) AS n FROM event_tags t"
            " JOIN events e ON e.uri = t.uri WHERE e.ends_at >= ?"
            " GROUP BY t.tag ORDER BY n DESC, value",
            now,
        )

    def list_groups(self, now: datetime) -> list[Count]:
        return self._counts(
            "SELECT grp AS value, COUNT(*) AS n FROM events"
            " WHERE ends_at >= ? AND grp IS NOT NULL AND grp != ''"
            " GROUP BY grp ORDER BY n DESC, value",
            now,
        )

    def _counts(self, sql: str, now: datetime) -> list[Count]:
        return [Count(value=r["value"], count=r["n"]) for r in self._all(sql, (to_iso(now),))]

    # updates

    def add_update(self, upd: EventUpdate) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO updates (event_uri, text, source_uri, created_at) VALUES (?, ?, ?, ?)",
                (upd.event_uri, upd.text, upd.source_uri, to_iso(upd.created_at)),
            )

    def list_updates(self, event_uri: str) -> list[EventUpdate]:
        rows = self._all(
            "SELECT * FROM updates WHERE event_uri = ? ORDER BY created_at, id", (event_uri,)
        )
        return [
            EventUpdate(
                event_uri=r["event_uri"],
                text=r["text"],
                source_uri=r["source_uri"],
                created_at=from_iso(r["created_at"]),
            )
            for r in rows
        ]

    # listeners

    def upsert_listener(self, listener: Listener) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO listeners (uri, author_did, record) VALUES (?, ?, ?)",
                (listener.uri, listener.author_did, listener.record.model_dump_json(by_alias=True)),
            )

    def delete_listener(self, uri: str) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM listeners WHERE uri = ?", (uri,)).rowcount > 0

    def listeners_for_did(self, did: str) -> list[Listener]:
        rows = self._all("SELECT * FROM listeners WHERE author_did = ? ORDER BY uri", (did,))
        return [
            Listener(
                uri=r["uri"],
                author_did=r["author_did"],
                record=ListenerRecord.model_validate_json(r["record"]),
            )
            for r in rows
        ]

    def listener_dids(self) -> list[str]:
        rows = self._all("SELECT DISTINCT author_did FROM listeners ORDER BY author_did")
        return [r["author_did"] for r in rows]

    # subscriptions

    def subscribe(self, subscriber_id: str, event_uri: str) -> None:
        with self._tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO subscriptions (subscriber_id, event_uri) VALUES (?, ?)",
                (subscriber_id, event_uri),
            )

    def unsubscribe(self, subscriber_id: str, event_uri: str) -> None:
        with self._tx() as c:
            c.execute(
                "DELETE FROM subscriptions WHERE subscriber_id = ? AND event_uri = ?",
                (subscriber_id, event_uri),
            )

    def subscribers_of(self, event_uri: str) -> list[str]:
        rows = self._all(
            "SELECT subscriber_id FROM subscriptions WHERE event_uri = ? ORDER BY subscriber_id",
            (event_uri,),
        )
        return [r["subscriber_id"] for r in rows]

    def subscriptions_of(self, subscriber_id: str) -> list[str]:
        rows = self._all(
            "SELECT event_uri FROM subscriptions WHERE subscriber_id = ? ORDER BY event_uri",
            (subscriber_id,),
        )
        return [r["event_uri"] for r in rows]

    # notifications

    def add_notification(self, n: Notification) -> Notification:
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO notifications (subscriber_id, event_uri, kind, message, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (n.subscriber_id, n.event_uri, n.kind, n.message, to_iso(n.created_at)),
            )
        return n.model_copy(update={"id": cur.lastrowid})

    def list_notifications(self, subscriber_id: str, since_id: int = 0) -> list[Notification]:
        rows = self._all(
            "SELECT * FROM notifications WHERE subscriber_id = ? AND id > ? ORDER BY id",
            (subscriber_id, since_id),
        )
        return [
            Notification(
                id=r["id"],
                subscriber_id=r["subscriber_id"],
                event_uri=r["event_uri"],
                kind=r["kind"],
                message=r["message"],
                created_at=from_iso(r["created_at"]),
            )
            for r in rows
        ]

    # ingest cursors

    def get_cursor(self, name: str) -> int | None:
        row = self._one("SELECT value FROM cursors WHERE name = ?", (name,))
        return row["value"] if row is not None else None

    def set_cursor(self, name: str, value: int) -> None:
        with self._tx() as c:
            c.execute("INSERT OR REPLACE INTO cursors (name, value) VALUES (?, ?)", (name, value))


def _purge(c: sqlite3.Connection, uris: list[str]) -> None:
    params = [(u,) for u in uris]
    for table, col in (
        ("events", "uri"),
        ("event_tags", "uri"),
        ("updates", "event_uri"),
        ("subscriptions", "event_uri"),
    ):
        c.executemany(f"DELETE FROM {table} WHERE {col} = ?", params)


def _row_to_event(row: sqlite3.Row) -> IndexedEvent:
    return IndexedEvent(
        uri=row["uri"],
        cid=row["cid"],
        author_did=row["author_did"],
        author_handle=row["author_handle"],
        source=row["source"],
        record=EventRecord.model_validate(json.loads(row["record"])),
        indexed_at=from_iso(row["indexed_at"]),
        updated_at=from_iso(row["updated_at"]),
    )
