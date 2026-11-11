from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings
from app.deps import get_app_settings
from app.models import EVENT_NSID, LISTENER_NSID

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@router.get("/config")
def config(settings: Annotated[Settings, Depends(get_app_settings)]) -> dict[str, object]:
    return {
        "devMode": settings.dev_mode,
        "jetstreamEnabled": settings.jetstream_enabled,
        "eventNsid": EVENT_NSID,
        "listenerNsid": LISTENER_NSID,
    }
