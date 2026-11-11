import asyncio

from app.api.subscriptions import sse_messages
from app.models import Notification

SUB = "subscriber-123"


def _body(uri: str, sub: str = SUB) -> dict[str, str]:
    return {"subscriberId": sub, "eventUri": uri}


def test_subscribe_list_unsubscribe(client, store, make_event):
    ev = make_event()
    store.upsert_event(ev)
    assert client.post("/api/subscriptions", json=_body(ev.uri)).status_code == 204
    assert client.get("/api/subscriptions", params={"subscriberId": SUB}).json() == [ev.uri]
    resp = client.request("DELETE", "/api/subscriptions", json=_body(ev.uri))
    assert resp.status_code == 204
    assert client.get("/api/subscriptions", params={"subscriberId": SUB}).json() == []


def test_subscribe_unknown_event_404(client):
    assert client.post("/api/subscriptions", json=_body("at://nope")).status_code == 404


def test_subscriber_id_validation(client, store, make_event):
    ev = make_event()
    store.upsert_event(ev)
    for bad in ["short", "x" * 65, "has space!"]:
        assert client.post("/api/subscriptions", json=_body(ev.uri, bad)).status_code == 422
        assert client.get("/api/subscriptions", params={"subscriberId": bad}).status_code == 422
    assert client.get("/api/notifications").status_code == 422


async def test_publish_persists_and_lists(client, store, notifier, make_event):
    ev = make_event()
    store.upsert_event(ev)
    store.subscribe(SUB, ev.uri)
    store.subscribe("other-subscriber", ev.uri)
    assert await notifier.publish(ev.uri, "updated", "Time changed") == 2
    assert await notifier.publish("at://no-subs", "updated", "x") == 0

    body = client.get("/api/notifications", params={"subscriberId": SUB}).json()
    assert len(body) == 1
    n = body[0]
    assert (n["subscriberId"], n["eventUri"], n["kind"], n["message"]) == (
        SUB, ev.uri, "updated", "Time changed",
    )  # fmt: skip
    since = client.get("/api/notifications", params={"subscriberId": SUB, "since": n["id"]})
    assert since.json() == []


async def test_publish_pushes_to_all_tabs(store, notifier):
    store.subscribe(SUB, "at://e")
    tab1, tab2 = notifier.connect(SUB), notifier.connect(SUB)
    await notifier.publish("at://e", "announcement", "Doors open")
    assert tab1.get_nowait().message == tab2.get_nowait().message == "Doors open"
    notifier.disconnect(SUB, tab1)
    await notifier.publish("at://e", "announcement", "Second")
    assert tab1.empty()
    assert tab2.get_nowait().message == "Second"
    notifier.disconnect(SUB, tab2)
    notifier.disconnect(SUB, tab2)  # idempotent


async def test_sse_messages_stream(store, notifier):
    store.subscribe(SUB, "at://e")
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    gen = sse_messages(notifier, SUB, is_disconnected, ping_interval_s=0.01)
    assert await anext(gen) == ": connected\n\n"
    assert await anext(gen) == ": ping\n\n"

    await notifier.publish("at://e", "deleted", "Cancelled")
    frame = await anext(gen)
    lines = frame.split("\n")
    assert lines[0].startswith("id: ")
    n = Notification.model_validate_json(lines[1].removeprefix("data: "))
    assert (n.kind, n.message, n.subscriber_id) == ("deleted", "Cancelled", SUB)

    disconnected = True
    await asyncio.sleep(0.02)
    assert [f async for f in gen] in ([], [": ping\n\n"])
    assert notifier._queues == {}


async def test_sse_releases_queue_on_close(notifier):
    async def never() -> bool:
        return False

    gen = sse_messages(notifier, SUB, never, ping_interval_s=10)
    await anext(gen)
    assert SUB in notifier._queues
    await gen.aclose()
    assert notifier._queues == {}


def test_stream_endpoint_validates(client):
    resp = client.get("/api/notifications/stream", params={"subscriberId": "bad"})
    assert resp.status_code == 422
