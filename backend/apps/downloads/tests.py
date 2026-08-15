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
