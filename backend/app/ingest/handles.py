"""DID -> handle resolution (did:plc via plc.directory, did:web via .well-known/did.json)."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

import httpx

log = logging.getLogger(__name__)


def did_document_url(did: str, plc_url: str = "https://plc.directory") -> str | None:
    if did.startswith("did:plc:"):
        return f"{plc_url}/{did}"
    if did.startswith("did:web:"):
        host, *path = did.removeprefix("did:web:").split(":")
        host = unquote(host)
        if not host:
            return None
        if path:
            return f"https://{host}/{'/'.join(path)}/did.json"
        return f"https://{host}/.well-known/did.json"
    return None


def handle_from_doc(doc: Any) -> str | None:
    aka = doc.get("alsoKnownAs") if isinstance(doc, dict) else None
    for entry in aka if isinstance(aka, list) else []:
        if isinstance(entry, str) and entry.startswith("at://") and len(entry) > 5:
            return entry.removeprefix("at://")
    return None


class HandleResolver:
    """Unverified handle lookup with an in-memory LRU + TTL cache. Never raises."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        ttl_s: float = 3600,
        max_size: int = 10_000,
        plc_url: str = "https://plc.directory",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=3.0)
        self.ttl_s, self.max_size, self.plc_url, self.clock = ttl_s, max_size, plc_url, clock
        self._cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()

    async def resolve(self, did: str) -> str | None:
        hit = self._cache.get(did)
        if hit is not None and hit[0] > self.clock():
            self._cache.move_to_end(did)
            return hit[1]
        handle = await self._fetch(did)
        self._remember(did, handle)
        return handle

    async def _fetch(self, did: str) -> str | None:
        url = did_document_url(did, self.plc_url)
        if url is None:
            return None
        try:
            resp = await self.client.get(url, timeout=3.0)
            resp.raise_for_status()
            return handle_from_doc(resp.json())
        except (httpx.HTTPError, ValueError) as e:
            log.info("handle resolution failed for %s: %r", did, e)
            return None

    def _remember(self, did: str, handle: str | None) -> None:
        self._cache[did] = (self.clock() + self.ttl_s, handle)
        self._cache.move_to_end(did)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    async def aclose(self) -> None:
        await self.client.aclose()
