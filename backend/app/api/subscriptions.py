import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.deps import get_notifier, get_store
from app.models import Notification
from app.notify.base import Notifier
from app.notify.service import SubscriptionNotifier
from app.store.base import EventStore

router = APIRouter(prefix="/api")

SUBSCRIBER_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
PING_INTERVAL_S = 15.0

Store = Annotated[EventStore, Depends(get_store)]
SubscriberIdQuery = Annotated[str, Query(alias="subscriberId", pattern=SUBSCRIBER_ID_PATTERN)]


class SubscriptionBody(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    subscriber_id: str = Field(pattern=SUBSCRIBER_ID_PATTERN)
    event_uri: str = Field(min_length=1, max_length=500)


def _notification_json(n: Notification) -> dict[str, Any]:
    return n.model_dump(mode="json", by_alias=True)


@router.post("/subscriptions", status_code=204)
def subscribe(body: SubscriptionBody, store: Store) -> Response:
    if store.get_event(body.event_uri) is None:
        raise HTTPException(status_code=404, detail="event not found")
    store.subscribe(body.subscriber_id, body.event_uri)
    return Response(status_code=204)


@router.delete("/subscriptions", status_code=204)
def unsubscribe(body: SubscriptionBody, store: Store) -> Response:
    store.unsubscribe(body.subscriber_id, body.event_uri)
    return Response(status_code=204)


@router.get("/subscriptions")
def list_subscriptions(subscriber_id: SubscriberIdQuery, store: Store) -> list[str]:
    return store.subscriptions_of(subscriber_id)


@router.get("/notifications")
def list_notifications(
    subscriber_id: SubscriberIdQuery,
    store: Store,
    since: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    return [_notification_json(n) for n in store.list_notifications(subscriber_id, since)]


async def sse_messages(
    notifier: SubscriptionNotifier,
    subscriber_id: str,
    is_disconnected: Callable[[], Awaitable[bool]],
    ping_interval_s: float = PING_INTERVAL_S,
) -> AsyncIterator[str]:
    """Yield SSE frames for one client until it disconnects; always releases its queue."""
    queue = notifier.connect(subscriber_id)
    try:
        yield ": connected\n\n"
        while not await is_disconnected():
            try:
                n = await asyncio.wait_for(queue.get(), timeout=ping_interval_s)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield f"id: {n.id}\ndata: {n.model_dump_json(by_alias=True)}\n\n"
    finally:
        notifier.disconnect(subscriber_id, queue)


@router.get("/notifications/stream")
async def stream_notifications(
    request: Request,
    subscriber_id: SubscriberIdQuery,
    notifier: Annotated[Notifier, Depends(get_notifier)],
) -> StreamingResponse:
    if not isinstance(notifier, SubscriptionNotifier):
        raise HTTPException(status_code=503, detail="live notifications unavailable")
    return StreamingResponse(
        sse_messages(notifier, subscriber_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
