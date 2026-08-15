"""Lightweight settings override for offline unit tests (SQLite, no Redis)."""

from config.settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
MEDIA_ROOT = "/tmp/download-bot-test-media"
INTERNAL_API_TOKEN = "test-token"
ALLOWED_TELEGRAM_IDS = []
