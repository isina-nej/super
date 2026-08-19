import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.downloads.services.base import DownloadError
from apps.downloads.services.classify import classify_url
from apps.downloads.services.cookies import json_cookies_to_netscape
from apps.downloads.services.media import (
    ensure_faststart,
    is_video_file,
    probe_media,
    trim_media_file,
)


class ClassifyUrlTests(SimpleTestCase):
    def test_youtube(self):
        self.assertEqual(
            classify_url("https://www.youtube.com/watch?v=abc"),
            "ytdlp",
        )

    def test_youtu_be(self):
        self.assertEqual(classify_url("https://youtu.be/abc"), "ytdlp")

    def test_direct_mp4(self):
        self.assertEqual(
            classify_url("https://cdn.example.com/path/file.mp4"),
            "direct",
        )

    def test_direct_zip(self):
        self.assertEqual(
            classify_url("https://example.org/a/b.zip?x=1"),
            "direct",
        )

    def test_tiktok(self):
        self.assertEqual(
            classify_url("https://www.tiktok.com/@user/video/123"),
            "ytdlp",
        )

    def test_pornhub(self):
        self.assertEqual(
            classify_url("https://www.pornhub.com/view_video.php?viewkey=abc"),
            "ytdlp",
        )


class CookieConvertTests(SimpleTestCase):
    def test_filters_unrelated_domains(self):
        cookies = [
            {
                "domain": ".pornhub.com",
                "hostOnly": False,
                "httpOnly": True,
                "name": "session",
                "path": "/",
                "secure": True,
                "session": False,
                "expirationDate": 2000000000,
                "value": "abc",
            },
            {
                "domain": "claude.ai",
                "hostOnly": True,
                "httpOnly": True,
                "name": "secret",
                "path": "/",
                "secure": True,
                "session": False,
                "expirationDate": 2000000000,
                "value": "nope",
            },
        ]
        out = json_cookies_to_netscape(cookies)
        self.assertIn("pornhub.com", out)
        self.assertIn("session", out)
        self.assertNotIn("claude.ai", out)
        self.assertNotIn("nope", out)


class CompactFormatTests(SimpleTestCase):
    def test_dedupes_heights_and_adds_best_audio(self):
        from apps.downloads.services.ytdlp import compact_format_choices

        info = {
            "formats": [
                {
                    "format_id": "18",
                    "height": 360,
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "ext": "mp4",
                },
                {
                    "format_id": "137",
                    "height": 1080,
                    "vcodec": "avc1",
                    "acodec": "none",
                    "ext": "mp4",
                },
                {"format_id": "sb0", "ext": "mhtml", "height": 180, "vcodec": "none", "acodec": "none"},
            ]
        }
        rows = compact_format_choices(info)
        ids = [r["id"] for r in rows]
        self.assertIn("18", ids)
        self.assertIn("137+bestaudio", ids)
        self.assertIn("best", ids)
        self.assertIn("audio", ids)
        self.assertTrue(all(r["id"] != "sb0" for r in rows))

    def test_twitter_http_empty_codec_is_kept(self):
        from apps.downloads.services.ytdlp import compact_format_choices

        info = {
            "formats": [
                {
                    "format_id": "http-2176",
                    "height": 720,
                    "vcodec": "",
                    "acodec": "",
                    "ext": "mp4",
                    "protocol": "https",
                    "filesize": 1288946799,
                },
                {
                    "format_id": "hls-520",
                    "height": 720,
                    "vcodec": "avc1",
                    "acodec": "none",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                },
            ]
        }
        rows = compact_format_choices(info)
        by_720 = next(r for r in rows if r["height"] == 720)
        self.assertEqual(by_720["id"], "http-2176")
        self.assertIn("GB", by_720["label"])


class FormatSelectorTests(SimpleTestCase):
    def test_pornhub_best_prefers_progressive_http(self):
        from apps.downloads.services.ytdlp import format_selector_for

        sel = format_selector_for("https://www.pornhub.com/view_video.php?viewkey=abc", "best")
        self.assertIn("protocol^=http", sel)

    def test_twitter_best_prefers_progressive_http(self):
        from apps.downloads.services.ytdlp import format_selector_for, _normalize_media_url

        sel = format_selector_for("https://x.com/user/status/1", "best")
        self.assertIn("protocol^=http", sel)
        self.assertEqual(
            _normalize_media_url("https://x.com/noisyb0y1/status/2087862674084258184/video/1"),
            "https://x.com/noisyb0y1/status/2087862674084258184",
        )

    def test_youtube_best_stays_generic(self):
        from apps.downloads.services.ytdlp import format_selector_for

        self.assertEqual(
            format_selector_for("https://www.youtube.com/watch?v=abc", "best"),
            "b/bv*+ba/best",
        )


class IsVideoFileTests(SimpleTestCase):
    def test_by_mime_type(self):
        self.assertTrue(is_video_file(Path("a.bin"), "video/mp4"))

    def test_by_extension(self):
        self.assertTrue(is_video_file(Path("a.mkv")))
        self.assertFalse(is_video_file(Path("a.jpg")))
        self.assertFalse(is_video_file(Path("a.zip")))


class EnsureFaststartTests(SimpleTestCase):
    def test_skips_non_mp4_containers(self):
        with patch("apps.downloads.services.media.subprocess.run") as run_mock:
            result = ensure_faststart(Path("clip.webm"))
        run_mock.assert_not_called()
        self.assertEqual(result, Path("clip.webm"))

    def test_replaces_original_on_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "video.mp4"
            src.write_bytes(b"original")

            def fake_run(cmd, **kwargs):
                Path(cmd[-1]).write_bytes(b"remuxed")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")

            with patch("apps.downloads.services.media.subprocess.run", side_effect=fake_run):
                result = ensure_faststart(src)

            self.assertEqual(result, src)
            self.assertEqual(src.read_bytes(), b"remuxed")
            # temp remux file should not linger next to the original
            self.assertEqual(list(Path(tmp_dir).iterdir()), [src])

    def test_falls_back_to_original_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "video.mp4"
            src.write_bytes(b"original")
            failed = subprocess.CompletedProcess([], 1, b"", b"boom")

            with patch("apps.downloads.services.media.subprocess.run", return_value=failed):
                result = ensure_faststart(src)

            self.assertEqual(result, src)
            self.assertEqual(src.read_bytes(), b"original")


class ProbeMediaTests(SimpleTestCase):
    def test_parses_ffprobe_json(self):
        payload = json.dumps(
            {
                "streams": [{"width": 1280, "height": 720}],
                "format": {"duration": "12.8"},
            }
        ).encode()
        proc = subprocess.CompletedProcess([], 0, payload, b"")
        with patch("apps.downloads.services.media.subprocess.run", return_value=proc):
            info = probe_media(Path("whatever.mp4"))
        self.assertEqual(info, {"width": 1280, "height": 720, "duration": 12})

    def test_returns_empty_dict_on_crash(self):
        with patch(
            "apps.downloads.services.media.subprocess.run",
            side_effect=OSError("no ffprobe"),
        ):
            info = probe_media(Path("whatever.mp4"))
        self.assertEqual(info, {})


class TrimMediaFileTests(SimpleTestCase):
    def test_replaces_original_on_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "video.mp4"
            src.write_bytes(b"full-video")

            def fake_run(cmd, **kwargs):
                Path(cmd[-1]).write_bytes(b"trimmed-clip")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")

            with patch("apps.downloads.services.media.subprocess.run", side_effect=fake_run):
                result = trim_media_file(src, 1000, 3000)

            self.assertEqual(result, src)
            self.assertEqual(src.read_bytes(), b"trimmed-clip")

    def test_raises_download_error_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "video.mp4"
            src.write_bytes(b"full-video")
            failed = subprocess.CompletedProcess([], 1, b"", b"nope")

            with patch("apps.downloads.services.media.subprocess.run", return_value=failed):
                with self.assertRaises(DownloadError):
                    trim_media_file(src, 1000, 3000)
