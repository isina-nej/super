from django.test import SimpleTestCase

from apps.downloads.services.classify import classify_url
from apps.downloads.services.cookies import json_cookies_to_netscape


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
