import unittest
from pathlib import Path

from media_urls import load_services, transformed_urls


SERVICES = load_services(Path(__file__).parents[1] / "media_services.json")


class TransformedUrlsTest(unittest.TestCase):
    def test_transforms_each_supported_service(self) -> None:
        cases = {
            "https://twitter.com/user/status/1": "https://fxtwitter.com/user/status/1",
            "https://x.com/user/status/1": "https://fixupx.com/user/status/1",
            "https://vm.tiktok.com/abc/": "https://d.tnktok.com/abc/",
            "https://reddit.com/r/test/comments/1": "https://vxreddit.com/r/test/comments/1",
            "https://www.instagram.com/reel/abc/": "https://kkinstagram.com/reel/abc/",
        }

        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(transformed_urls(original, SERVICES), [expected])

    def test_preserves_query_and_fragment(self) -> None:
        text = "https://instagram.com/p/abc/?utm_source=test#comments"
        self.assertEqual(
            transformed_urls(text, SERVICES),
            ["https://kkinstagram.com/p/abc/?utm_source=test#comments"],
        )

    def test_transforms_multiple_urls_in_order(self) -> None:
        text = (
            "First https://instagram.com/reel/one, then "
            "https://www.tiktok.com/@user/video/2."
        )
        self.assertEqual(
            transformed_urls(text, SERVICES),
            [
                "https://kkinstagram.com/reel/one",
                "https://d.tnktok.com/@user/video/2",
            ],
        )

    def test_supports_www_url_without_scheme(self) -> None:
        self.assertEqual(
            transformed_urls("www.instagram.com/p/abc", SERVICES),
            ["https://kkinstagram.com/p/abc"],
        )

    def test_keeps_balanced_parentheses_and_trims_message_punctuation(self) -> None:
        text = "Watch (https://reddit.com/r/test/comments/a_(b))."
        self.assertEqual(
            transformed_urls(text, SERVICES),
            ["https://vxreddit.com/r/test/comments/a_(b)"],
        )

    def test_ignores_unsupported_and_deceptive_hosts(self) -> None:
        text = (
            "https://example.com/x https://instagram.com.evil.example/reel/1 "
            "https://youtu.be/abc"
        )
        self.assertEqual(transformed_urls(text, SERVICES), [])


if __name__ == "__main__":
    unittest.main()
