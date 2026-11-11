"""Notifier interface: ingest calls publish(); the API streams results to clients."""

from __future__ import annotations

from typing import Protocol

from app.models import NotificationKind


class Notifier(Protocol):
    async def publish(self, event_uri: str, kind: NotificationKind, message: str) -> int:
        """Fan out to every subscriber of event_uri (persist + live push). Returns count."""
        ...
