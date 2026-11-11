"""Composition root: builds the store, notifier and ingest pipeline and mounts the routers."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import dev, events, imports, meta, subscriptions
from app.config import Settings, get_settings
from app.expiry import run_expiry_loop
from app.ingest.handles import HandleResolver
from app.ingest.ical import run_ical_loop
from app.ingest.jetstream import JetstreamClient
from app.ingest.processor import CommitProcessor
from app.notify.service import SubscriptionNotifier
from app.store.sqlite import SqliteStore

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, background: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = SqliteStore(settings.db_path)
        notifier = SubscriptionNotifier(store)
        resolver = HandleResolver()
        processor = CommitProcessor(store, notifier, resolver)
        app.state.settings, app.state.store = settings, store
        app.state.notifier, app.state.processor = notifier, processor

        tasks: list[asyncio.Task] = []
        if background:
            tasks.append(asyncio.create_task(run_expiry_loop(store, notifier, settings)))
            tasks.append(asyncio.create_task(run_ical_loop(store, notifier, settings)))
            if settings.jetstream_enabled:
                client = JetstreamClient(settings.jetstream_url, processor, store)
                tasks.append(asyncio.create_task(client.run_forever()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await resolver.aclose()
            store.close()

    app = FastAPI(title="Community Map AppView", version="0.1.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (meta, events, subscriptions, imports, dev):
        app.include_router(module.router)

    frontend = Path(settings.frontend_dir)
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:
        log.warning("frontend dir %s not found; serving API only", frontend)
    return app


app = create_app()
