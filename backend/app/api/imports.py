"""POST /api/import/ical: import events from an iCalendar feed on demand."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.deps import get_notifier, get_store
from app.ingest.ical import import_feed
from app.ingest.netguard import is_public_url
from app.notify.base import Notifier
from app.store.base import EventStore

router = APIRouter(prefix="/api")


class IcalImportRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        parts = urlsplit(v.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("url must be an http(s) URL")
        return v.strip()


class IcalImportResponse(BaseModel):
    imported: int


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def get_url_guard() -> Callable[[str], bool]:
    return is_public_url


@router.post("/import/ical")
async def import_ical(
    body: IcalImportRequest,
    url_guard: Annotated[Callable[[str], bool], Depends(get_url_guard)],
    store: Annotated[EventStore, Depends(get_store)],
    notifier: Annotated[Notifier, Depends(get_notifier)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> IcalImportResponse:
    if not url_guard(body.url):
        raise HTTPException(422, "url must point to a public host")
    try:
        n = await import_feed(body.url, store, notifier, client)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"could not fetch feed: {e}") from e
    except ValueError as e:
        raise HTTPException(502, "feed is not a valid iCalendar file") from e
    return IcalImportResponse(imported=n)
