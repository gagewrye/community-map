"""FastAPI dependencies. main.py puts the concrete objects on app.state."""

from fastapi import Request

from app.config import Settings
from app.notify.base import Notifier
from app.store.base import EventStore


def get_store(request: Request) -> EventStore:
    return request.app.state.store


def get_notifier(request: Request) -> Notifier:
    return request.app.state.notifier


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
