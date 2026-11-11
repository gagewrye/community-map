from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_store
from app.models import EventQuery
from app.store.base import EventStore
from app.views import event_view, update_view

router = APIRouter(prefix="/api")

Store = Annotated[EventStore, Depends(get_store)]


@router.get("/events")
def list_events(
    store: Store,
    tag: Annotated[list[str], Query(max_length=32)] = [],  # noqa: B006 (FastAPI copies it)
    group: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    before: datetime | None = None,
    after: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=1000)] = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    query = EventQuery(
        tags=tag,
        group=group or None,
        text=q or None,
        starts_before=before,
        ends_after=after,
        limit=limit,
        cursor=cursor or None,
    )
    try:
        page = store.query_events(query, now)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="invalid cursor") from e
    return {"events": [event_view(ev, now) for ev in page.events], "cursor": page.cursor}


@router.get("/event")
def get_event(uri: str, store: Store) -> dict[str, Any]:
    ev = store.get_event(uri)
    if ev is None:
        raise HTTPException(status_code=404, detail="event not found")
    view = event_view(ev, datetime.now(UTC))
    view["updates"] = [update_view(u) for u in store.list_updates(uri)]
    return view


@router.get("/tags")
def list_tags(store: Store) -> list[dict[str, Any]]:
    return [c.model_dump() for c in store.list_tags(datetime.now(UTC))]


@router.get("/groups")
def list_groups(store: Store) -> list[dict[str, Any]]:
    return [c.model_dump() for c in store.list_groups(datetime.now(UTC))]
