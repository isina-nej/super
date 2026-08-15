from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    telegram_bot_api_url: str = "http://telegram-bot-api:8081"
    api_base_url: str = "http://api:8000/api/v1"
    internal_api_token: str = "change-me-internal-token"
    allowed_telegram_ids: str = ""
    required_channel: str = "@CoffeeMan_nej"
    required_channel_url: str = "https://t.me/CoffeeMan_nej"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 1800.0
    media_root: str = "/media"

    @property
    def allowed_ids(self) -> set[int]:
        if not self.allowed_telegram_ids.strip():
            return set()
        result: set[int] = set()
        for part in self.allowed_telegram_ids.split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
        return result

    @property
    def local_api_base(self) -> str:
        """Base URL for Bot API including /bot<token> prefix handled by aiogram."""
        return self.telegram_bot_api_url.rstrip("/")


@lru_cache
def get_settings() -> BotSettings:
    return BotSettings(
        bot_token=os.getenv("BOT_TOKEN", ""),
        telegram_bot_api_url=os.getenv(
            "TELEGRAM_BOT_API_URL", "http://telegram-bot-api:8081"
        ),
        api_base_url=os.getenv("API_BASE_URL", "http://api:8000/api/v1"),
        internal_api_token=os.getenv("INTERNAL_API_TOKEN", "change-me-internal-token"),
        allowed_telegram_ids=os.getenv("ALLOWED_TELEGRAM_IDS", ""),
        required_channel=os.getenv("REQUIRED_CHANNEL", "@CoffeeMan_nej"),
        required_channel_url=os.getenv(
            "REQUIRED_CHANNEL_URL", "https://t.me/CoffeeMan_nej"
        ),
        poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "2")),
        poll_timeout_seconds=float(os.getenv("POLL_TIMEOUT_SECONDS", "1800")),
        media_root=os.getenv("MEDIA_ROOT", "/media"),
    )
