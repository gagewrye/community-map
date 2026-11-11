from __future__ import annotations

import httpx

from app.ingest.handles import HandleResolver, did_document_url, handle_from_doc


def resolver(
    handler: httpx.MockTransport, clock: list[float] | None = None, **kw: object
) -> HandleResolver:
    t = clock if clock is not None else [0.0]
    return HandleResolver(httpx.AsyncClient(transport=handler), clock=lambda: t[0], **kw)  # type: ignore[arg-type]


def doc(handle: str) -> dict[str, object]:
    return {"id": "x", "alsoKnownAs": [f"at://{handle}"]}


def test_did_document_url() -> None:
    assert did_document_url("did:plc:abc") == "https://plc.directory/did:plc:abc"
    assert did_document_url("did:web:example.com") == "https://example.com/.well-known/did.json"
    assert (
        did_document_url("did:web:localhost%3A8080")
        == "https://localhost:8080/.well-known/did.json"
    )
    assert did_document_url("did:web:ex.com:u:alice") == "https://ex.com/u/alice/did.json"
    assert did_document_url("did:key:z6Mk") is None


def test_handle_from_doc() -> None:
    assert handle_from_doc({"alsoKnownAs": ["https://x", "at://alice.test"]}) == "alice.test"
    assert handle_from_doc({"alsoKnownAs": "at://nope"}) is None
    assert handle_from_doc([]) is None


async def test_resolve_plc_and_web() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        if req.url.host == "plc.directory":
            return httpx.Response(200, json=doc("alice.test"))
        return httpx.Response(200, json=doc("bob.example.com"))

    r = resolver(httpx.MockTransport(handle))
    assert await r.resolve("did:plc:alice") == "alice.test"
    assert await r.resolve("did:web:example.com") == "bob.example.com"


async def test_failures_return_none() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        if "500" in str(req.url):
            return httpx.Response(500)
        if "junk" in str(req.url):
            return httpx.Response(200, text="<html>")
        raise httpx.ConnectTimeout("slow")

    r = resolver(httpx.MockTransport(handle))
    assert await r.resolve("did:plc:500") is None
    assert await r.resolve("did:plc:junk") is None
    assert await r.resolve("did:plc:timeout") is None
    assert await r.resolve("did:key:abc") is None


async def test_cache_ttl_and_lru() -> None:
    calls: list[str] = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(200, json=doc("h" + req.url.path[-1]))

    clock = [0.0]
    r = resolver(httpx.MockTransport(handle), clock, ttl_s=10, max_size=2)
    await r.resolve("did:plc:a")
    await r.resolve("did:plc:a")
    assert len(calls) == 1
    clock[0] = 11
    await r.resolve("did:plc:a")
    assert len(calls) == 2
    await r.resolve("did:plc:b")
    await r.resolve("did:plc:c")  # evicts a (least recently used)
    await r.resolve("did:plc:b")
    assert len(calls) == 4
    await r.resolve("did:plc:a")
    assert len(calls) == 5
