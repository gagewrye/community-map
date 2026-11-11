import asyncio
from datetime import timedelta

from app.config import Settings
from app.expiry import run_expiry_loop, sweep_once


async def test_sweep_notifies_then_deletes(store, notifier, make_event, now):
    old = make_event("old", name="Taco Tuesday", start_h=-3, end_h=-1)
    live = make_event("live", start_h=-1, end_h=1)
    store.upsert_event(old)
    store.upsert_event(live)
    store.subscribe("subscriber1", old.uri)
    store.subscribe("subscriber1", live.uri)
    queue = notifier.connect("subscriber1")

    assert await sweep_once(store, notifier, now, grace_s=0) == [old.uri]

    [n] = store.list_notifications("subscriber1")
    assert (n.kind, n.event_uri, n.message) == ("expired", old.uri, "Taco Tuesday has ended")
    assert queue.get_nowait() == n
    assert store.get_event(old.uri) is None
    assert store.get_event(live.uri) is not None


async def test_sweep_respects_grace(store, notifier, make_event, now):
    ev = make_event(start_h=-2, end_h=-0.5)
    store.upsert_event(ev)
    assert await sweep_once(store, notifier, now, grace_s=3600) == []
    assert await sweep_once(store, notifier, now + timedelta(hours=1), grace_s=3600) == [ev.uri]


async def test_sweep_many_pages(store, notifier, make_event, now):
    for i in range(130):
        store.upsert_event(make_event(f"e{i:03d}", start_h=-3, end_h=-1))
    assert len(await sweep_once(store, notifier, now, grace_s=0)) == 130


class BoomStore:
    def __init__(self) -> None:
        self.calls = 0

    def query_events(self, q, now):
        self.calls += 1
        raise RuntimeError("boom")


async def test_loop_survives_exceptions(notifier):
    store = BoomStore()
    settings = Settings(expiry_interval_s=0)
    task = asyncio.create_task(run_expiry_loop(store, notifier, settings))
    for _ in range(20):
        await asyncio.sleep(0)
    task.cancel()
    assert store.calls >= 2
