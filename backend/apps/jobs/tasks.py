from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.downloads.services.router import download_url
from apps.jobs.models import DownloadJob

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, soft_time_limit=3600, time_limit=3900)
def process_download_job(self, job_id: int) -> dict:
    try:
        job = DownloadJob.objects.select_related("user").get(pk=job_id)
    except DownloadJob.DoesNotExist:
        logger.error("Job %s not found", job_id)
        return {"ok": False, "error": "not_found"}

    if job.status not in {DownloadJob.Status.PENDING, DownloadJob.Status.DOWNLOADING}:
        return {"ok": False, "error": f"invalid_status:{job.status}"}

    job.status = DownloadJob.Status.DOWNLOADING
    job.progress = 1
    job.save(update_fields=["status", "progress", "updated_at"])

    dest_dir = Path(settings.MEDIA_ROOT) / "jobs" / str(job.id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(percent: int) -> None:
        # Avoid thrashing DB; update every ~5%
        if percent <= job.progress:
            return
        if percent - job.progress < 5 and percent < 95:
            return
        DownloadJob.objects.filter(pk=job.id).update(
            progress=min(percent, 99),
            updated_at=timezone.now(),
        )
        job.progress = percent

    try:
        result = download_url(
            url=job.url,
            dest_dir=dest_dir,
            source_type=job.source_type or None,
            preferred_format=job.preferred_format,
            max_bytes=settings.MAX_FILE_SIZE_BYTES,
            progress_callback=on_progress,
        )
    except Exception as exc:  # noqa: BLE001 — surface to job.error
        logger.exception("Download failed for job %s", job_id)
        job.mark_failed(str(exc) or "دانلود ناموفق بود.")
        return {"ok": False, "error": str(exc)}

    file_path = Path(result.file_path)
    if not file_path.exists():
        job.mark_failed("فایل دانلود شده پیدا نشد.")
        return {"ok": False, "error": "missing_file"}

    size = file_path.stat().st_size
    if size > settings.MAX_FILE_SIZE_BYTES:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        job.mark_failed(
            f"حجم فایل ({size} بایت) از سقف ۲ گیگابایت بیشتر است."
        )
        return {"ok": False, "error": "too_large"}

    job.status = DownloadJob.Status.READY
    job.file_path = str(file_path)
    job.file_size = size
    job.mime_type = result.mime_type or ""
    job.title = (result.title or "")[:512]
    job.source_type = result.source_type
    job.progress = 100
    job.completed_at = timezone.now()
    job.error = ""
    job.save(
        update_fields=[
            "status",
            "file_path",
            "file_size",
            "mime_type",
            "title",
            "source_type",
            "progress",
            "completed_at",
            "error",
            "updated_at",
        ]
    )
    return {"ok": True, "job_id": job.id, "file_path": job.file_path}
