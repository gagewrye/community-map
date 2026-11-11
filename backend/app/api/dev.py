"""POST /api/dev/records: feed a Jetstream-shaped commit straight to the processor (dev only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.config import Settings
from app.deps import get_app_settings
from app.ingest.processor import CommitProcessor

router = APIRouter(prefix="/api")


def get_processor(request: Request) -> CommitProcessor:
    return request.app.state.processor


def require_dev_mode(settings: Annotated[Settings, Depends(get_app_settings)]) -> None:
    if not settings.dev_mode:
        raise HTTPException(404, "Not Found")


@router.post("/dev/records", dependencies=[Depends(require_dev_mode)])
async def post_dev_record(
    msg: Annotated[dict[str, Any], Body()],
    processor: Annotated[CommitProcessor, Depends(get_processor)],
) -> dict[str, bool]:
    await processor.handle(msg)
    return {"ok": True}
