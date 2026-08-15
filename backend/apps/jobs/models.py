from django.conf import settings
from django.db import models

from apps.accounts.models import TelegramUser


class DownloadJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DOWNLOADING = "downloading", "Downloading"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        ACKED = "acked", "Acked"
        CANCELED = "canceled", "Canceled"

    class SourceType(models.TextChoices):
        YTDLP = "ytdlp", "yt-dlp"
        DIRECT = "direct", "Direct HTTP"

    class PreferredFormat(models.TextChoices):
        BEST = "best", "Best quality"
        AUDIO = "audio", "Audio only"

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    url = models.URLField(max_length=2048)
    chat_id = models.BigIntegerField()
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    source_type = models.CharField(
        max_length=16,
        choices=SourceType.choices,
        blank=True,
        default="",
    )
    preferred_format = models.CharField(
        max_length=64,
        default=PreferredFormat.BEST,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    file_path = models.CharField(max_length=1024, blank=True, default="")
    file_size = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=255, blank=True, default="")
    title = models.CharField(max_length=512, blank=True, default="")
    error = models.TextField(blank=True, default="")
    progress = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"DownloadJob({self.pk}, {self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in {self.Status.PENDING, self.Status.DOWNLOADING}

    def mark_failed(self, message: str) -> None:
        self.status = self.Status.FAILED
        self.error = message[:4000]
        self.save(update_fields=["status", "error", "updated_at"])
