from django.test import SimpleTestCase

from apps.downloads.services.classify import classify_url


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
