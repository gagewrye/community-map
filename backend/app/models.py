"""Shared domain models. This file is the contract between ingest, store and API.

Lexicon record JSON is camelCase; Python attributes are snake_case. Use
`model_validate(record_json)` to parse and `model_dump(by_alias=True)` to emit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

EVENT_NSID = "app.communitymap.event"
LISTENER_NSID = "app.communitymap.listener"
POST_NSID = "app.bsky.feed.post"


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Location(_Camel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    lat: str | None = None
    lng: str | None = None

    @field_validator("lat", "lng")
    @classmethod
    def _numeric(cls, v: str | None) -> str | None:
        if v is not None:
            float(v)  # raises ValueError -> validation error
        return v


class EventRecord(_Camel):
    """Exactly the app.communitymap.event lexicon record."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=3000)
    starts_at: datetime
    ends_at: datetime
    location: Location
    tags: list[str] = Field(default_factory=list, max_length=10)
    group: str | None = Field(default=None, max_length=100)
    source_url: str | None = None
    created_at: datetime

    @field_validator("tags")
    @classmethod
    def _norm_tags(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for t in v:
            t = t.strip().lstrip("#").lower()[:32]
            if t and t not in out:
                out.append(t)
        return out

    @model_validator(mode="after")
    def _window(self) -> EventRecord:
        if self.ends_at < self.starts_at:
            raise ValueError("endsAt must be >= startsAt")
        return self


Source = Literal["atproto", "ical"]


class IndexedEvent(_Camel):
    """An event as stored in our index (AppView)."""

    uri: str  # at://did/app.communitymap.event/rkey, or ical://<feed>/<uid>
    cid: str | None = None
    author_did: str
    author_handle: str | None = None
    source: Source = "atproto"
    record: EventRecord
    indexed_at: datetime
    updated_at: datetime


class ListenerRecord(_Camel):
    subject: str
    hashtag: str = Field(min_length=1, max_length=64)
    created_at: datetime

    @field_validator("hashtag")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lstrip("#").lower()


class Listener(_Camel):
    uri: str
    author_did: str
    record: ListenerRecord


class EventUpdate(_Camel):
    """An announcement attached to an event (e.g. from a Bluesky post via a listener)."""

    event_uri: str
    text: str
    source_uri: str | None = None  # at:// URI of the originating post
    created_at: datetime


NotificationKind = Literal["updated", "deleted", "announcement", "expired"]


class Notification(_Camel):
    id: int | None = None
    subscriber_id: str
    event_uri: str
    kind: NotificationKind
    message: str
    created_at: datetime


class EventQuery(_Camel):
    tags: list[str] = Field(default_factory=list)  # match ANY of these tags
    group: str | None = None
    text: str | None = None  # case-insensitive substring over name/description/location
    starts_before: datetime | None = None
    ends_after: datetime | None = None  # default: now (hide expired)
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None  # opaque, from Page.cursor


class Page(_Camel):
    events: list[IndexedEvent]
    cursor: str | None = None


class Count(_Camel):
    value: str
    count: int
