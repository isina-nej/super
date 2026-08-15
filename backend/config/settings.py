"""Django settings for the Telegram download bot API."""

from __future__ import annotations

import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

pymysql.install_as_MySQLdb()
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
# Project root (parent of backend/) — shared media volume mounts here
PROJECT_ROOT = BASE_DIR.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.accounts",
    "apps.jobs",
    "apps.downloads",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "download_bot"),
        "USER": os.getenv("MYSQL_USER", "bot"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", "botpass"),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(PROJECT_ROOT / "media")))
MEDIA_URL = "/media/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Bot / download settings ---
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "change-me-internal-token")
ALLOWED_TELEGRAM_IDS = [
    int(x.strip())
    for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",")
    if x.strip().isdigit()
]
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_CONCURRENT_JOBS_PER_USER = int(os.getenv("MAX_CONCURRENT_JOBS_PER_USER", "2"))
DOWNLOAD_JOB_TTL_HOURS = int(os.getenv("DOWNLOAD_JOB_TTL_HOURS", "24"))
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "")
YTDLP_PROXY = os.getenv("YTDLP_PROXY", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.jobs.permissions.InternalTokenPermission",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "UNAUTHENTICATED_USER": None,
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}
