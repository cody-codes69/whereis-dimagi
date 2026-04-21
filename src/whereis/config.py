"""Environment-driven configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

StrategyName = Literal["population", "proximity", "first"]
SmsAdapter = Literal["simulator", "twilio"]
EmailAdapter = Literal["simulator", "mailgun", "imap"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WHEREIS_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/whereis.db")
    geonames_dump_url: str = "https://download.geonames.org/export/dump/cities15000.zip"
    geonames_dump_file: str = "cities15000.txt"

    default_strategy: StrategyName = "population"

    sms_adapter: SmsAdapter = "simulator"
    email_adapter: EmailAdapter = "simulator"
    twilio_auth_token: str | None = None
    twilio_verify_signature: bool = False

    imap_host: str = "imap.gmail.com"
    imap_user: str | None = None
    imap_password: str | None = None
    imap_mailbox: str = "INBOX"
    imap_poll_seconds: int = 60

    max_speed_kmh: float = 950.0
    homebody_radius_km: float = 200.0
    physics_enforce: bool = False

    shared_secret: str | None = None


settings = Settings()
