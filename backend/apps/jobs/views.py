from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import TelegramUser
from apps.downloads.services.classify import classify_url
from apps.downloads.services.ytdlp import list_ytdlp_formats
from apps.jobs.models import DownloadJob
from apps.jobs.serializers import (
    CreateJobSerializer,
    DownloadJobSerializer,
    ProbeSerializer,
)
from apps.jobs.tasks import process_download_job


def _user_allowed(telegram_id: int) -> bool:
    allowed = settings.ALLOWED_TELEGRAM_IDS
    if not allowed:
        return True
    return telegram_id in allowed


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "download-bot-api"})


class JobListCreateView(APIView):
    def post(self, request: Request) -> Response:
        serializer = CreateJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        telegram_id = data["telegram_user_id"]
        if not _user_allowed(telegram_id):
            return Response(
                {"detail": "دسترسی مجاز نیست. شناسه تلگرام شما در لیست مجاز نیست."},
                status=status.HTTP_403_FORBIDDEN,
            )

        active_count = DownloadJob.objects.filter(
            user__telegram_id=telegram_id,
            status__in=[DownloadJob.Status.PENDING, DownloadJob.Status.DOWNLOADING],
        ).count()
        if active_count >= settings.MAX_CONCURRENT_JOBS_PER_USER:
            return Response(
                {
                    "detail": (
                        f"حداکثر {settings.MAX_CONCURRENT_JOBS_PER_USER} دانلود همزمان مجاز است. "
                        "لطفاً صبر کنید."
                    )
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        source_type = classify_url(data["url"])
        user, _ = TelegramUser.objects.update_or_create(
            telegram_id=telegram_id,
            defaults={
                "username": data.get("username") or "",
                "first_name": data.get("first_name") or "",
                "last_name": data.get("last_name") or "",
                "language_code": data.get("language_code") or "",
                "is_active": True,
            },
        )

        job = DownloadJob.objects.create(
            user=user,
            url=data["url"],
            chat_id=data["chat_id"],
            preferred_format=data.get("preferred_format") or DownloadJob.PreferredFormat.BEST,
            source_type=source_type,
            status=DownloadJob.Status.PENDING,
        )
        async_result = process_download_job.delay(job.id)
        job.celery_task_id = str(getattr(async_result, "id", "") or "")[:255]
        job.save(update_fields=["celery_task_id"])
        return Response(DownloadJobSerializer(job).data, status=status.HTTP_201_CREATED)


class JobDetailView(APIView):
    def get(self, request: Request, job_id: int) -> Response:
        try:
            job = DownloadJob.objects.select_related("user").get(pk=job_id)
        except DownloadJob.DoesNotExist:
            return Response({"detail": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(DownloadJobSerializer(job).data)


class JobAckView(APIView):
    def post(self, request: Request, job_id: int) -> Response:
        try:
            job = DownloadJob.objects.get(pk=job_id)
        except DownloadJob.DoesNotExist:
            return Response({"detail": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        if job.status not in {DownloadJob.Status.READY, DownloadJob.Status.ACKED}:
            return Response(
                {"detail": f"Cannot ack job in status '{job.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.downloads.cleanup import cleanup_job_file

        cleanup_job_file(job.file_path)
        job.status = DownloadJob.Status.ACKED
        job.file_path = ""
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "file_path", "completed_at", "updated_at"])
        return Response(DownloadJobSerializer(job).data)


class JobCancelView(APIView):
    def post(self, request: Request, job_id: int) -> Response:
        try:
            job = DownloadJob.objects.get(pk=job_id)
        except DownloadJob.DoesNotExist:
            return Response({"detail": "Job not found"}, status=status.HTTP_404_NOT_FOUND)

        if job.status not in {DownloadJob.Status.PENDING, DownloadJob.Status.DOWNLOADING}:
            return Response(
                {"detail": f"جاب در وضعیت '{job.status}' قابل لغو نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = DownloadJob.Status.CANCELED
        job.error = "دانلود توسط کاربر لغو شد."
        job.save(update_fields=["status", "error", "updated_at"])

        if job.celery_task_id:
            try:
                from celery import current_app

                current_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
            except Exception:  # noqa: BLE001
                pass

        from apps.downloads.cleanup import cleanup_job_file

        cleanup_job_file(job.file_path)
        return Response(DownloadJobSerializer(job).data)


class ProbeView(APIView):
    def post(self, request: Request) -> Response:
        serializer = ProbeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        telegram_id = data.get("telegram_user_id") or 0
        if telegram_id and not _user_allowed(telegram_id):
            return Response(
                {"detail": "دسترسی مجاز نیست."},
                status=status.HTTP_403_FORBIDDEN,
            )

        url = data["url"]
        source_type = classify_url(url)
        if source_type == "direct":
            return Response(
                {
                    "url": url,
                    "source_type": "direct",
                    "title": "",
                    "formats": [
                        {"id": "best", "label": "دانلود فایل", "height": 0, "ext": ""},
                    ],
                }
            )
        try:
            probed = list_ytdlp_formats(url)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "url": url,
                "source_type": "ytdlp",
                "title": probed.get("title") or "",
                "formats": probed.get("formats") or [],
            }
        )
