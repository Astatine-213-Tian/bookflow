from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.notion.cms import ensure_work
from tests.notion_api import BlockAPI, display_names, mcp_schema

AUTHOR = "11111111-1111-1111-1111-111111111111"
WORK = "22222222-2222-2222-2222-222222222222"
AUTHORS_DS = "33333333-3333-3333-3333-333333333333"
WORKS_DS = "44444444-4444-4444-4444-444444444444"
TEMPLATE = "55555555-5555-4555-8555-555555555555"
URL = "https://www.jjwxc.net/oneauthor.php?authorid=123"
CONFIG = {
    "databases": {
        "authors": {"data_source_id": AUTHORS_DS, "view_id": "authors"},
        "works": {"data_source_id": WORKS_DS, "view_id": "works"},
    }
}


def reader(homepage=URL, catalog_homepage=True):
    return SimpleNamespace(
        catalog=AsyncMock(
            return_value={
                "works": {"default_template": WORK},
                "authors": {
                    "properties": (
                        {"homepage": {"name": "作者主页", "type": "url"}}
                        if catalog_homepage
                        else {}
                    )
                },
            }
        ),
        rows=AsyncMock(side_effect=[[], []]),
        create_page=AsyncMock(side_effect=[AUTHOR, WORK]),
        ensure_options=AsyncMock(),
        page=AsyncMock(
            return_value=SimpleNamespace(
                data_source_id=AUTHORS_DS,
                properties={"title": "作者", "homepage": homepage},
            )
        ),
    )


def plain(rich_text):
    return "".join(r.get("plain_text") or r["text"]["content"] for r in rich_text)


class Workspace(BlockAPI):
    """Catalog MCP reads and writes by current display name over the REST fake."""

    def __init__(self, renamed):
        super().__init__()
        self.options = {}
        self.mcp_creates = []
        self.add_source(AUTHORS_DS, "authors", renamed.get("authors"))
        self.add_source(WORKS_DS, "works", renamed.get("works"))

    def names(self, data_source):
        kind, renamed, _ = self.sources[data_source]
        return display_names(kind, renamed)

    async def call(self, name, arguments):
        if name == "notion-fetch":
            id = arguments["id"]
            if id.startswith("view://"):
                ds = AUTHORS_DS if id == "view://authors" else WORKS_DS
                config = {"dataSourceUrl": "collection://" + ds}
                return {"text": "<view>\n" + json.dumps(config) + "\n</view>"}
            ds = id.removeprefix("collection://")
            kind, renamed, omit = self.sources[ds]
            state = {"default_page_template": TEMPLATE} if ds == WORKS_DS else {}
            options = self.options.get(ds, {})
            return {"text": mcp_schema(kind, renamed, omit, options, **state)}
        if name == "notion-query-data-sources":
            view = arguments["data"]["view_url"]
            ds = AUTHORS_DS if view == "view://authors" else WORKS_DS
            title = self.names(ds)["title"]
            rows = [
                {"url": id, title: plain(page["properties"][title]["title"])}
                for id, page in self.pages.items()
                if page["parent"]["data_source_id"] == ds
            ]
            return {"results": rows, "has_more": False}
        if name == "notion-update-data-source":
            ds = arguments["data_source_id"]
            fields = {name: field for field, name in self.names(ds).items()}
            for statement in arguments["statements"].split("; "):
                column, values = re.fullmatch(
                    r'ALTER COLUMN "(.+)" SET (?:MULTI_)?SELECT\((.*)\)', statement
                ).groups()
                self.options.setdefault(ds, {})[fields[column]] = [
                    {"name": option.rsplit(":", 1)[0].strip("'")}
                    for option in values.split(", ")
                    if option
                ]
            return {}
        if name == "notion-create-pages":
            ds = arguments["parent"]["data_source_id"]
            page = arguments["pages"][0]
            if set(page["properties"]) - set(self.names(ds).values()):
                raise AssertionError("MCP create used a stale property name")
            self.mcp_creates.append(page)
            return {"pages": [{"id": WORK}]}
        raise AssertionError((name, arguments))


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
                        book,
                        Path(temp) / "state.json",
                        CONFIG,
                        tools=SimpleNamespace(call_api=AsyncMock()),
                    )
                properties = remote.create_page.call_args_list[0].args[2]
                self.assertEqual(
                    properties,
                    {"title": "作者", **({"homepage": URL} if homepage else {})},
                )
                self.assertEqual(book["work_id"], WORK)
                self.assertNotIn("pending_author", book)
                if homepage:
                    remote.page.assert_awaited_once_with(AUTHOR, "authors")

    async def test_found_homepage_requires_the_catalog_homepage_property(self):
        remote = reader(catalog_homepage=False)
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.cms.NotionBooks", return_value=remote),
            patch(
                "src.notion.cms.MetadataLookup.find_author_homepage", return_value=URL
            ),
        ):
            with self.assertRaisesRegex(ValueError, "homepage URL property"):
                await ensure_work(
                    {"metadata": {"title": "书", "creator": "作者"}},
                    Path(temp) / "state.json",
                    CONFIG,
                    tools=SimpleNamespace(call_api=AsyncMock()),
                )
        remote.create_page.assert_not_awaited()

    async def test_renamed_columns_still_create_and_verify_the_author(self):
        # The homepage column was once renamed from 晋江主页 to 作者主页, which
        # broke name-keyed callers. Any display name must keep working.
        api = Workspace(
            {
                "authors": {"title": "笔名", "homepage": "个人主页"},
                "works": {"title": "书名", "subjects": "分类", "language": "文种"},
            }
        )
        book = {"metadata": {"title": "书", "creator": "作者", "subjects": ["爱情"]}}
        with (
            tempfile.TemporaryDirectory() as temp,
            patch(
                "src.notion.cms.MetadataLookup.find_author_homepage", return_value=URL
            ),
        ):
            await ensure_work(book, Path(temp) / "state.json", CONFIG, tools=api)
        [author] = [
            page
            for page in api.pages.values()
            if page["parent"]["data_source_id"] == AUTHORS_DS
        ]
        self.assertEqual(author["properties"]["个人主页"]["url"], URL)
        self.assertEqual(plain(author["properties"]["笔名"]["title"]), "作者")
        self.assertEqual(book["work_id"], WORK)
        self.assertNotIn("pending_author", book)
        [work] = api.mcp_creates
        self.assertEqual(work["properties"]["书名"], "书")
        self.assertEqual(work["properties"]["文种"], "zh-CN")
        self.assertEqual([o["name"] for o in api.options[WORKS_DS]["subjects"]], ["爱情"])

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
                    tools=SimpleNamespace(call_api=AsyncMock()),
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
                await ensure_work(
                    book, state, CONFIG, tools=SimpleNamespace(call_api=AsyncMock())
                )
            self.assertEqual(book["pending_author"], "作者")
            self.assertNotIn("work_id", book)
            remote.rows.side_effect = [[{"id": AUTHOR, "title": "作者"}], []]
            remote.page.return_value.properties["homepage"] = URL
            await ensure_work(
                book, state, CONFIG, tools=SimpleNamespace(call_api=AsyncMock())
            )
            lookup.assert_called_once()
        self.assertEqual(remote.create_page.await_count, 2)  # One author, one work.
        self.assertEqual(book["work_id"], WORK)

    async def test_existing_author_is_reused_without_a_lookup_or_overwrite(self):
        remote = reader()
        remote.rows.side_effect = [[{"id": AUTHOR, "title": "作者"}], []]
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
                tools=SimpleNamespace(call_api=AsyncMock()),
            )
            lookup.assert_not_called()
        remote.create_page.assert_awaited_once()
        self.assertEqual(remote.create_page.call_args.args[0], WORKS_DS)


if __name__ == "__main__":
    unittest.main()
