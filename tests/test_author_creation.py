from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.notion.cms import AUTHOR_HOMEPAGE, ensure_work

AUTHOR = "11111111-1111-1111-1111-111111111111"
WORK = "22222222-2222-2222-2222-222222222222"
AUTHORS_DS = "33333333-3333-3333-3333-333333333333"
WORKS_DS = "44444444-4444-4444-4444-444444444444"
URL = "https://www.jjwxc.net/oneauthor.php?authorid=123"
CONFIG = {
    "databases": {
        "authors": {"data_source_id": AUTHORS_DS, "view_id": "authors"},
        "works": {"data_source_id": WORKS_DS, "view_id": "works"},
    }
}


def reader(homepage=URL):
    return SimpleNamespace(
        catalog=AsyncMock(
            return_value={
                "works": {"default_template": WORK},
                "authors": {"properties": {AUTHOR_HOMEPAGE: {"type": "url"}}},
            }
        ),
        rows=AsyncMock(side_effect=[[], []]),
        create_page=AsyncMock(side_effect=[AUTHOR, WORK]),
        ensure_options=AsyncMock(),
        page=AsyncMock(
            return_value=SimpleNamespace(
                data_source_id=AUTHORS_DS,
                properties={"作者": "作者", AUTHOR_HOMEPAGE: homepage},
            )
        ),
    )


class AuthorCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_author_includes_verified_homepage_when_found(self):
        for homepage in (URL, None):
            with self.subTest(homepage=homepage), tempfile.TemporaryDirectory() as temp:
                book = {"metadata": {"title": "书", "creator": "作者"}}
                remote = reader(homepage)
                with (
                    patch("src.notion.cms.NotionBooks", return_value=remote),
                    patch(
                        "src.notion.cms.MetadataLookup.find_author_homepage",
                        return_value=homepage,
                    ),
                ):
                    await ensure_work(
                        book, Path(temp) / "state.json", CONFIG, tools=None
                    )
                properties = remote.create_page.call_args_list[0].args[1]
                self.assertEqual(
                    properties,
                    {"作者": "作者", **({AUTHOR_HOMEPAGE: URL} if homepage else {})},
                )
                self.assertEqual(book["work_id"], WORK)
                self.assertNotIn("pending_author", book)
                if homepage:
                    remote.page.assert_awaited_once_with(AUTHOR)

    async def test_lookup_failure_stops_before_creating_an_empty_author(self):
        remote = reader()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.cms.NotionBooks", return_value=remote),
            patch(
                "src.notion.cms.MetadataLookup.find_author_homepage",
                side_effect=OSError("lookup failed"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "lookup failed"):
                await ensure_work(
                    {"metadata": {"title": "书", "creator": "作者"}},
                    Path(temp) / "state.json",
                    CONFIG,
                    tools=None,
                )
        remote.create_page.assert_not_awaited()

    async def test_failed_readback_resumes_the_existing_author_without_recreating(self):
        book = {"metadata": {"title": "书", "creator": "作者"}}
        remote = reader("")
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.cms.NotionBooks", return_value=remote),
            patch(
                "src.notion.cms.MetadataLookup.find_author_homepage", return_value=URL
            ) as lookup,
        ):
            state = Path(temp) / "state.json"
            with self.assertRaisesRegex(ValueError, "homepage readback differs"):
                await ensure_work(book, state, CONFIG, tools=None)
            self.assertEqual(book["pending_author"], "作者")
            self.assertNotIn("work_id", book)
            remote.rows.side_effect = [[{"id": AUTHOR, "作者": "作者"}], []]
            remote.page.return_value.properties[AUTHOR_HOMEPAGE] = URL
            await ensure_work(book, state, CONFIG, tools=None)
            lookup.assert_called_once()
        self.assertEqual(remote.create_page.await_count, 2)  # One author, one work.
        self.assertEqual(book["work_id"], WORK)

    async def test_existing_author_is_reused_without_a_lookup_or_overwrite(self):
        remote = reader()
        remote.rows.side_effect = [[{"id": AUTHOR, "作者": "作者"}], []]
        remote.create_page.side_effect = [WORK]
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.cms.NotionBooks", return_value=remote),
            patch("src.notion.cms.MetadataLookup.find_author_homepage") as lookup,
        ):
            await ensure_work(
                {"metadata": {"title": "书", "creator": "作者"}},
                Path(temp) / "state.json",
                CONFIG,
                tools=None,
            )
            lookup.assert_not_called()
        remote.create_page.assert_awaited_once()
        self.assertEqual(remote.create_page.call_args.args[0], WORKS_DS)


if __name__ == "__main__":
    unittest.main()
