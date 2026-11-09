from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from src.crawler.providers.pili45 import parser


class FakePage:
    def __init__(self, title: str, ready: bool) -> None:
        self.title, self.ready = title, ready

    async def evaluate(self, script: str):
        return self.title if script == "document.title" else self.ready

    async def get_content(self) -> str:
        return "<html></html>"


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def get(self, url: str) -> FakePage:
        return self.page


async def no_sleep(_seconds: float) -> None:
    return None


class Pili45FetcherTests(unittest.TestCase):
    def fetch(self, page: FakePage, *, headless: bool) -> str:
        fetcher = parser.Fetcher(headless=headless, delay=0)
        fetcher.browser = FakeBrowser(page)
        with mock.patch.object(parser.asyncio, "sleep", no_sleep):
            return asyncio.run(fetcher.get_html("https://www.pili45.com/5/1/info.html"))

    def test_challenge_page_fails_instead_of_yielding_an_empty_book(self):
        with self.assertRaisesRegex(RuntimeError, "Just a moment.*without --headless"):
            self.fetch(FakePage("Just a moment...", False), headless=True)

    def test_headed_failure_names_the_page_without_headless_hint(self):
        with self.assertRaises(RuntimeError) as caught:
            self.fetch(FakePage("Just a moment...", False), headless=False)
        self.assertNotIn("--headless", str(caught.exception))

    def test_ready_page_returns_content(self):
        self.assertEqual(
            self.fetch(FakePage("小蘑菇", True), headless=True), "<html></html>"
        )


if __name__ == "__main__":
    unittest.main()
