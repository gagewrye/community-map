"""Runtime settings, read from environment variables prefixed CM_ (e.g. CM_DB_PATH)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CM_")

    db_path: str = "data/communitymap.db"
    # Jetstream (AT Protocol firehose, JSON flavour). Disabled = index only via dev/import.
    jetstream_enabled: bool = False
    jetstream_url: str = "wss://jetstream2.us-east.bsky.network/subscribe"
    # Dev mode exposes POST /api/dev/records to simulate firehose commits locally.
    dev_mode: bool = False
    # Seconds between expiry sweeps; events are dropped once endsAt + grace has passed.
    expiry_interval_s: int = 60
    expiry_grace_s: int = 0
    # Comma-separated iCal URLs polled every ical_interval_s.
    ical_feeds: str = ""
    ical_interval_s: int = 900
    frontend_dir: str = "../frontend"
    cors_origins: str = "*"


def get_settings() -> Settings:
    return Settings()
