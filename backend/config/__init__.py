try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover — celery optional until deps installed
    celery_app = None

__all__ = ("celery_app",)
