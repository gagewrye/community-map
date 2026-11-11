"""Notifier that persists one Notification per subscriber and pushes to live SSE queues."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.models import Notification, NotificationKind
from app.store.base import EventStore

log = logging.getLogger(__name__)

QUEUE_MAXSIZE = 100


class SubscriptionNotifier:
    def __init__(self, store: EventStore) -> None:
        self._store = store
        self._queues: dict[str, set[asyncio.Queue[Notification]]] = {}

    async def publish(self, event_uri: str, kind: NotificationKind, message: str) -> int:
        now = datetime.now(UTC)
        subscribers = self._store.subscribers_of(event_uri)
        for sub in subscribers:
            n = self._store.add_notification(
                Notification(
                    subscriber_id=sub,
                    event_uri=event_uri,
                    kind=kind,
                    message=message,
                    created_at=now,
                )
            )
            self._push(sub, n)
        return len(subscribers)

    def _push(self, subscriber_id: str, n: Notification) -> None:
        for queue in self._queues.get(subscriber_id, ()):
            try:
                queue.put_nowait(n)
            except asyncio.QueueFull:
                log.warning("dropping live notification for slow client %s", subscriber_id)

    def connect(self, subscriber_id: str) -> asyncio.Queue[Notification]:
        queue: asyncio.Queue[Notification] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._queues.setdefault(subscriber_id, set()).add(queue)
        return queue

    def disconnect(self, subscriber_id: str, queue: asyncio.Queue[Notification]) -> None:
        queues = self._queues.get(subscriber_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self._queues[subscriber_id]
