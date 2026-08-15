from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import TelegramUser
from apps.jobs.models import DownloadJob


@override_settings(INTERNAL_API_TOKEN="test-token", ALLOWED_TELEGRAM_IDS=[])
class JobsApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.auth = {"HTTP_AUTHORIZATION": "Bearer test-token"}

    def test_health_no_auth(self):
        r = self.client.get("/api/v1/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_create_job_requires_auth(self):
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://www.youtube.com/watch?v=abc",
                "telegram_user_id": 1,
                "chat_id": 1,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    @patch("apps.jobs.views.process_download_job.delay")
    def test_create_and_get_job(self, delay_mock):
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://www.youtube.com/watch?v=abc",
                "telegram_user_id": 42,
                "chat_id": 99,
                "preferred_format": "audio",
                "username": "tester",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["source_type"], "ytdlp")
        self.assertEqual(data["preferred_format"], "audio")
        delay_mock.assert_called_once_with(data["id"])

        detail = self.client.get(f"/api/v1/jobs/{data['id']}/", **self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["telegram_user_id"], 42)

    @patch("apps.jobs.views.process_download_job.delay")
    def test_create_job_accepts_ytdlp_format_id(self, delay_mock):
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://www.pornhub.com/view_video.php?viewkey=abc",
                "telegram_user_id": 42,
                "chat_id": 99,
                "preferred_format": "hls-3116+bestaudio",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["preferred_format"], "hls-3116+bestaudio")
        detail = self.client.get(f"/api/v1/jobs/{r.json()['id']}/", **self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["preferred_format"], "hls-3116+bestaudio")

    @patch("apps.jobs.views.process_download_job.delay")
    def test_direct_url_classified(self, delay_mock):
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://cdn.example.com/file.mp4",
                "telegram_user_id": 7,
                "chat_id": 7,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["source_type"], "direct")

    @override_settings(ALLOWED_TELEGRAM_IDS=[100])
    @patch("apps.jobs.views.process_download_job.delay")
    def test_allowed_ids_enforced(self, delay_mock):
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://cdn.example.com/file.mp4",
                "telegram_user_id": 1,
                "chat_id": 1,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(r.status_code, 403)

    @patch("apps.downloads.cleanup.cleanup_job_file")
    def test_ack_ready_job(self, cleanup_mock):
        user = TelegramUser.objects.create(telegram_id=55)
        job = DownloadJob.objects.create(
            user=user,
            url="https://cdn.example.com/a.mp4",
            chat_id=55,
            status=DownloadJob.Status.READY,
            source_type="direct",
            file_path="/media/jobs/1/a.mp4",
        )
        r = self.client.post(f"/api/v1/jobs/{job.id}/ack/", **self.auth)
        self.assertEqual(r.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, DownloadJob.Status.ACKED)
        cleanup_mock.assert_called_once()

    @patch("apps.jobs.views.process_download_job.delay")
    def test_cancel_pending_job(self, delay_mock):
        delay_mock.return_value.id = "task-1"
        r = self.client.post(
            "/api/v1/jobs/",
            {
                "url": "https://cdn.example.com/file.mp4",
                "telegram_user_id": 9,
                "chat_id": 9,
            },
            format="json",
            **self.auth,
        )
        job_id = r.json()["id"]
        DownloadJob.objects.filter(pk=job_id).update(status=DownloadJob.Status.DOWNLOADING)
        cancel = self.client.post(f"/api/v1/jobs/{job_id}/cancel/", **self.auth)
        self.assertEqual(cancel.status_code, 200, cancel.content)
        self.assertEqual(cancel.json()["status"], "canceled")

    @patch("apps.jobs.views.list_ytdlp_formats")
    def test_probe_ytdlp(self, probe_mock):
        probe_mock.return_value = {
            "title": "Demo",
            "formats": [{"id": "18", "label": "360p", "height": 360, "ext": "mp4"}],
        }
        r = self.client.post(
            "/api/v1/probes/",
            {"url": "https://www.youtube.com/watch?v=abc", "telegram_user_id": 1},
            format="json",
            **self.auth,
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["title"], "Demo")
        self.assertEqual(r.json()["formats"][0]["id"], "18")
