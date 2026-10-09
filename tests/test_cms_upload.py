from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from lxml import etree as ET
from notion_books import NotionError, work_properties
from PIL import Image

from src.content.models import Chapter, Volume
from src.crawler.models import CrawledBook
from src.epub.writer import export_local
from src.notion.cms import STORAGE, chapter_entries, ensure_views, ensure_work
from src.notion.cover import finish_cover, upload_cover, validate_cover, verify_cover
from src.notion.upload import UPLOAD_CONCURRENCY, upload_draft, upload_row, upload_rows
from src.runtime.files import digest
from src.workflows.ingest import OutputOptions, write_outputs
from tests.fixtures import isolated_workdir, prepared_crawl as prepare_crawl
from tests.notion_api import BlockAPI, paragraphs

WORK = "11111111-1111-1111-1111-111111111111"
DS = "22222222-2222-2222-2222-222222222222"


def source():
    book = prepare_crawl(
        title="书",
        author="作者",
        source_url="https://example.org/book",
        intro_paragraphs=["简介内容"],
        volumes=[
            Volume("卷一", [Chapter("第1章", ["正文"]), Chapter("第2章", ["后续"])]),
            Volume("番外", [Chapter("番外篇", ["独立番外"], role="extra")]),
        ],
    )
    book["identifier"] = "local-book"
    return book


def png():
    data = io.BytesIO()
    Image.new("RGB", (2, 3), "blue").save(data, format="PNG")
    return data.getvalue()


class DestinationTests(unittest.TestCase):
    def setUp(self):
        isolated_workdir(self)

    def test_local_path_never_authenticates_and_retains_thumbnail_only(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "local.epub"
            with (
                patch("src.workflows.prepare.enrich_source", return_value={}),
                patch(
                    "src.notion.upload.upload_source",
                    side_effect=AssertionError("Notion called"),
                ),
            ):
                write_outputs(
                    CrawledBook(
                        title="书",
                        author="作者",
                        source_url="https://example.org/book",
                        volumes=[
                            Volume("卷一", [Chapter("第1章", ["正文"])]),
                            Volume("番外", [Chapter("番外", ["内容"])]),
                        ],
                        cover_bytes=png(),
                        cover_mime="image/png",
                    ),
                    OutputOptions(output_formats=("epub",), output=out),
                )
            with zipfile.ZipFile(out) as z:
                self.assertEqual(z.read("EPUB/cover.png"), png())
                self.assertFalse(
                    any(
                        Path(n).name in ("cover.xhtml", "cover.html")
                        for n in z.namelist()
                    )
                )
                root = ET.fromstring(z.read("EPUB/content.opf"))
                images = root.xpath(
                    '//*[local-name()="item" and @properties="cover-image"]'
                )
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].get("href"), "cover.png")
                self.assertEqual(root.find("{*}spine")[0].get("idref"), "nav")
                self.assertIn("番外", z.read("EPUB/nav.xhtml").decode())
                self.assertIn("内容", z.read("EPUB/chapter_0002.xhtml").decode())

    def test_bilingual_builder_embeds_only_cover_image(self):
        from src.workflows.translation import build_bilingual_epub
        from tests.fixtures import write_source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_source(root, ["Text."], cover=png())
            build_bilingual_epub(
                snapshot_dir=root,
                translations_dir=root / "translations",
                output=root / "bilingual.epub",
            )
            with zipfile.ZipFile(root / "bilingual.epub") as z:
                self.assertEqual(z.read("EPUB/cover.png"), png())
                self.assertFalse(
                    any(
                        Path(n).name in {"cover.xhtml", "cover.html"}
                        for n in z.namelist()
                    )
                )
                opf = ET.fromstring(z.read("EPUB/content.opf"))
                self.assertEqual(
                    len(
                        opf.xpath(
                            '//*[local-name()="item" and @properties="cover-image"]'
                        )
                    ),
                    1,
                )
                self.assertFalse(
                    opf.xpath('//*[local-name()="itemref" and @idref="cover"]')
                )

    def test_cms_metadata_has_new_field_types_and_no_service_fields(self):
        self.assertEqual(source()["metadata"]["description"], "简介内容")
        metadata = source()["metadata"] | {
            "date": "2020-02-01",
            "series": "系列",
            "series_position": "1.5",
            "subjects": ["爱情", "耽美"],
            "description": "摘要",
        }
        props = work_properties(metadata, [WORK, DS])
        self.assertEqual(props["作者"], [WORK, DS])
        self.assertEqual(props["系列序号"], 1.5)
        self.assertEqual(props["书籍分类"], ["爱情", "耽美"])
        self.assertEqual(props["date:出版日期:start"], "2020-02-01")
        self.assertEqual(props["来源"], "https://example.org/book")
        self.assertNotIn("发表日期", props)
        self.assertFalse(any("发布" in key or "Bookshelf" in key for key in props))

    def test_cms_rejects_deeper_toc_without_flattening_local_structure(self):
        book = source()
        book["sections"] = [
            {"title": "部", "children": copy.deepcopy(book["sections"])}
        ]
        with self.assertRaisesRegex(ValueError, "one parent"):
            chapter_entries(book)
        with tempfile.TemporaryDirectory() as directory:
            export_local(book, Path(directory) / "book.epub")

    def test_cms_outline_rejects_missing_duplicate_and_shared_chapters(self):
        for kind in ("missing", "duplicate", "shared"):
            with self.subTest(kind=kind):
                book = source()
                member = next(iter(book["chapters"]))
                if kind == "missing":
                    book["chapters"]["unlisted"] = copy.deepcopy(
                        book["chapters"][member]
                    )
                elif kind == "duplicate":
                    book["sections"].append({"member": member})
                else:
                    book["chapters"][member]["shared"] = True
                with self.assertRaises(ValueError):
                    chapter_entries(book)


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_importer_applies_language_default_without_changing_checkpoint_source(
        self,
    ):
        for language in (None, "", "en"):
            with self.subTest(language=language):
                book = source()
                book["metadata"].pop("language", None)
                if language is not None:
                    book["metadata"]["language"] = language
                original = copy.deepcopy(book["metadata"])
                config = {
                    "databases": {
                        "works": {"data_source_id": DS, "view_id": "works"},
                        "authors": {"data_source_id": DS, "view_id": "authors"},
                    }
                }
                tools = AsyncMock()
                tools.call.return_value = {"pages": [{"id": WORK}]}
                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch(
                        "notion_books.NotionBooks.catalog",
                        new=AsyncMock(
                            return_value={"works": {"default_template": WORK}}
                        ),
                    ),
                    patch(
                        "notion_books.NotionBooks.rows",
                        new=AsyncMock(
                            side_effect=[
                                [{"id": WORK, "作者": original["creator"]}],
                                [],
                            ]
                        ),
                    ),
                    patch("notion_books.NotionBooks.ensure_options", new=AsyncMock()),
                ):
                    await ensure_work(
                        book, Path(directory) / "import.json", config, tools=tools
                    )
                properties = tools.call.call_args.args[1]["pages"][0]["properties"]
                self.assertEqual(properties["语言"], language or "zh-CN")
                self.assertEqual(book["metadata"], original)
                self.assertEqual(
                    book["template_request"],
                    {"template_id": WORK, "status": "requested"},
                )
                self.assertEqual(
                    tools.call.call_args.args[1]["pages"][0]["template_id"], WORK
                )

    async def test_template_discovery_selects_manual_views_over_display_views(self):
        chapter_database = "33333333-3333-4333-8333-333333333333"
        manual = "44444444-4444-4444-8444-444444444444"
        sorted_view = "55555555-5555-4555-8555-555555555555"
        extras_database = "66666666-6666-4666-8666-666666666666"
        extras_source = "77777777-7777-4777-8777-777777777777"
        extras_view = "88888888-8888-4888-8888-888888888888"
        book = {"work_id": WORK}
        config = {
            "databases": {
                "works": {"data_source_id": WORK},
                "extras": {"data_source_id": extras_source},
            }
        }

        def view(data_source, **options):
            return {
                "text": "<view>\n"
                + json.dumps(
                    {"dataSourceUrl": "collection://" + data_source, **options}
                )
                + "\n</view>"
            }

        documents = {
            WORK: {
                "text": f'<parent-data-source url="collection://{WORK}"/>\n<properties>\n{{}}\n</properties>\n<content>\n<database url="{chapter_database}"/>\n<database url="{extras_database}"/>\n</content>'
            },
            chapter_database: {
                "text": f'<parent-page url="{WORK}"/> view://{sorted_view} view://{manual}'
            },
            extras_database: {"text": "view://" + extras_view},
            "collection://" + DS: {
                "url": chapter_database,
                "text": '<data-source-state>\n{"name":"正文","schema":{"章节":{"type":"title"},"所属标题":{"type":"select"}}}\n</data-source-state>',
            },
            "view://" + manual: view(DS),
            "view://" + sorted_view: view(DS, sorts=[{"property": "章节"}]),
            "view://" + extras_view: view(
                extras_source,
                advancedFilter={
                    "type": "property",
                    "property": "涉及作品",
                    "propertyType": "relation",
                    "operator": "relation_contains",
                    "value": {"type": "exact", "value": WORK},
                },
            ),
        }

        class Tools:
            async def call(self, name, arguments):
                if name != "notion-fetch":
                    raise AssertionError("Unexpected write during discovery")
                return documents[arguments["id"]]

        with tempfile.TemporaryDirectory() as directory:
            await ensure_views(
                book, Path(directory) / "import.json", config, tools=Tools()
            )
        self.assertEqual(book["chapters_view_id"], manual)
        self.assertEqual(book["view_id"], extras_view)

    async def test_draft_creation_matches_cms_order_and_resumes_without_overwrite(self):
        book = source()
        book.update(
            storage=STORAGE,
            catalog_id=DS,
            work_id=WORK,
            chapters_data_source_id=DS,
            chapters_view_id="main",
            view_id="extras",
        )
        config = {
            "databases": {
                "works": {"data_source_id": DS},
                "extras": {"data_source_id": DS, "view_id": "all-extras"},
            }
        }
        rows = {"main": [], "extras": [], "all-extras": []}
        created = {}
        calls = []

        api = BlockAPI()

        class Tools:
            async def call_api(self, request):
                response = await api(request)
                if request["method"] == "POST" and request["path"] == "pages":
                    self.record(response["body"]["id"], {
                        "properties": {
                            name: (
                                "".join(run["text"]["content"] for run in value["title"])
                                if "title" in value else
                                [r["id"] for r in value["relation"]]
                                if "relation" in value else
                                value["select"]["name"] if value["select"] else None
                            )
                            for name, value in request["json"]["properties"].items()
                        }
                    })
                return response

            def record(self, id, page):
                calls.append(page)
                created[id] = page
                view = "main" if "章节" in page["properties"] else "extras"
                rows[view].insert(0, {"id": id})

            async def call(self, name, args):
                if name != "notion-create-pages":
                    raise AssertionError("Unexpected write: " + name)
                page = args["pages"][0]
                id = f"00000000-0000-0000-0000-{len(created) + 1:012d}"
                props = {}
                for name, value in page["properties"].items():
                    if isinstance(value, list):
                        props[name] = {
                            "type": "relation",
                            "relation": [{"id": x} for x in value],
                            "has_more": False,
                        }
                    elif name not in ("章节", "番外"):
                        props[name] = {"type": "select", "select": {"name": value}}
                title_field = "章节" if "章节" in page["properties"] else "番外"
                api.add_page(
                    id, page["properties"][title_field], DS, title_field, props
                )
                self.record(id, page)
                return {"pages": [{"id": id}]}

        async def read_rows(_reader, view):
            return rows[view]

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("src.notion.upload.ensure_work", new=AsyncMock()),
            patch("src.notion.upload.ensure_views", new=AsyncMock()),
            patch("src.notion.presentation.ensure_volume_colors", new=AsyncMock()),
            patch("notion_books.NotionBooks.ensure_options", new=AsyncMock()),
            patch("notion_books.NotionBooks.rows", read_rows),
            patch(
                "notion_books.NotionBooks.inventory",
                new=AsyncMock(return_value=[]),
            ),
        ):
            state = Path(directory) / "import.json"
            await upload_draft(book, state, config, tools=Tools())
            self.assertTrue(book["uploaded"])
            self.assertEqual(
                [created[r["id"]]["properties"]["章节"] for r in rows["main"]],
                ["简介", "第一章", "第二章"],
            )
            self.assertEqual(
                created[rows["main"][1]["id"]]["properties"]["所属标题"], "卷一"
            )
            count = len(calls)
            edited = rows["main"][1]["id"]
            node = api.nodes[api.children[edited][0]]
            node["paragraph"]["rich_text"][0]["text"]["content"] = (
                "User edit after upload"
            )
            await upload_draft(book, state, config, tools=Tools())
            self.assertEqual(len(calls), count)
            # Appending to a nonempty manual view creates at the top. Stop for
            # deliberate reordering, then resume using the existing page ID.
            from src.notion.update import apply_update
            from tests.fixtures import paragraph

            request = {
                "version": 1,
                "id": "append-3",
                "book_id": book["identifier"],
                "operations": [
                    {
                        "kind": "append_chapter",
                        "chapter_id": "new",
                        "after": "chapter-1-2",
                        "chapter": {"title": "第3章", "blocks": [paragraph("新章。")]},
                    }
                ],
            }
            with self.assertRaisesRegex(ValueError, "manual order"):
                await apply_update(state, request, config, tools=Tools())
            resumed = json.loads(state.read_text())
            new_id = resumed["chapters"]["new"]["page_id"]
            self.assertEqual(rows["main"][0]["id"], new_id)
            self.assertEqual(len(calls), count + 1)
            rows["main"].append(rows["main"].pop(0))
            await apply_update(state, request, config, tools=Tools())
            self.assertEqual(len(calls), count + 1)
            self.assertTrue(json.loads(state.read_text())["uploaded"])
            self.assertIn(
                "User edit after upload",
                [
                    n[n["type"]]["rich_text"][0]["text"]["content"]
                    for n in api.nodes.values()
                    if n[n["type"]].get("rich_text")
                ],
            )

    async def test_lost_create_response_stops_retry_without_duplicate(self):
        book = source()
        item = next(iter(book["chapters"].values()))
        tools = AsyncMock()
        tools.call_api.side_effect = TimeoutError("response lost")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "import.json"
            kwargs = {
                "data_source": DS,
                "properties": {"章节": item["title"]},
                "title_property": "章节",
                "tools": tools,
            }
            with self.assertRaises(NotionError) as caught:
                await upload_row(item, book, state, **kwargs)
            self.assertTrue(caught.exception.uncertain)
            self.assertIsInstance(caught.exception.__cause__, TimeoutError)
            self.assertTrue(item["pending"])
            with self.assertRaisesRegex(ValueError, "response was lost"):
                await upload_row(item, book, state, **kwargs)
            self.assertEqual(tools.call_api.await_count, 1)
            tools.call.assert_not_awaited()

    async def test_body_workers_are_bounded_and_drain_after_failure(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                started, finished = [], []
                full = asyncio.Event()
                release = asyncio.Event()
                active = 0
                peak = 0

                async def row(*, item, **kwargs):
                    nonlocal active, peak
                    started.append(item)
                    active += 1
                    peak = max(peak, active)
                    if active == UPLOAD_CONCURRENCY:
                        full.set()
                    await release.wait()
                    active -= 1
                    finished.append(item)
                    if fail and item == 0:
                        raise ValueError("row failed")

                with patch("src.notion.upload.upload_row", side_effect=row):
                    run = asyncio.create_task(upload_rows(
                        [{"item": i} for i in range(25)], {}, Path("unused"),
                        tools=None, destinations={},
                    ))
                    await asyncio.wait_for(full.wait(), 2)
                    self.assertEqual(len(started), UPLOAD_CONCURRENCY)
                    self.assertFalse(run.done())
                    release.set()
                    if fail:
                        with self.assertRaisesRegex(ValueError, "row failed"):
                            await run
                        self.assertEqual(len(started), UPLOAD_CONCURRENCY)
                    else:
                        await run
                        self.assertEqual(len(started), 25)
                self.assertEqual(peak, UPLOAD_CONCURRENCY)
                self.assertCountEqual(started, finished)

    async def test_initial_body_read_is_reused_and_editor_content_is_preserved(self):
        from tests.notion_api import PAGE, write
        from notion_books import NotionBooks

        for existing in ("", "正文", "Editor changed this"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                book = source()
                item = next(iter(book["chapters"].values()))
                item.update(page_id=PAGE, blocks=paragraphs("正文"))
                api = BlockAPI()
                api.add_page(PAGE, item["title"], DS)
                if existing:
                    await write(NotionBooks(api=api), paragraphs(existing))
                api.calls.clear()
                before = api.mutations
                kwargs = dict(
                    data_source=DS, properties={"章节": item["title"]},
                    title_property="章节", tools=api,
                )
                if existing == "Editor changed this":
                    with self.assertRaisesRegex(ValueError, "editor content"):
                        await upload_row(item, book, Path(directory) / "import.json", **kwargs)
                    self.assertEqual(api.mutations, before)
                    self.assertNotIn("content_write", item)
                else:
                    await upload_row(item, book, Path(directory) / "import.json", **kwargs)
                    self.assertTrue(item["verified"])
                    if existing:
                        self.assertEqual(api.mutations, before)
                    page_reads = [r for r in api.calls if r["method"] == "GET" and r["path"].startswith("pages/")]
                    self.assertEqual(len(page_reads), 2)

    async def test_old_catalog_state_cannot_be_written(self):
        with self.assertRaisesRegex(ValueError, "old library"):
            await upload_draft(
                source(),
                Path("unused.json"),
                {"databases": {"works": {"data_source_id": DS}}},
                tools=None,
            )

    async def test_native_cover_uses_rest_for_upload_and_readback(self):
        cover = png()
        requests = []

        async def handler(request):
            requests.append(request)
            if request.url.host == "files.example.org":
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, content=cover)
            self.assertEqual(request.headers["authorization"], "Bearer test-token")
            if request.url.path.endswith("/send"):
                self.assertIn(b'filename="cover.png"', request.content)
                return httpx.Response(200, json={"status": "uploaded"})
            if request.method == "PATCH":
                self.assertEqual(
                    json.loads(request.content),
                    {"cover": {"type": "file_upload", "file_upload": {"id": DS}}},
                )
            return httpx.Response(200, json={"id": DS})

        client = httpx.AsyncClient

        def factory(**kwargs):
            return client(transport=httpx.MockTransport(handler), **kwargs)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"NOTION_API_TOKEN": "test-token"}),
            patch("src.notion.cover.httpx.AsyncClient", factory),
        ):
            asset = Path(directory) / "cover.png"
            asset.write_bytes(cover)
            book = {
                "work_id": WORK,
                "cover_asset": str(asset),
                "cover_sha256": digest(cover),
            }
            tools = AsyncMock()
            tools.call_api.side_effect = [
                {"status": 200, "body": payload}
                for payload in [
                    {
                        "object": "page",
                        "id": WORK,
                        "properties": {},
                        "last_edited_time": "0",
                        "cover": None,
                    },
                    {
                        "object": "page",
                        "id": WORK,
                        "properties": {},
                        "last_edited_time": "0",
                        "cover": {
                            "type": "file",
                            "file": {"url": "https://files.example.org/cover"},
                        },
                    },
                ]
            ]
            await upload_cover(book, Path(directory) / "import.json", tools=tools)
            self.assertTrue(book["cover_uploaded"])
            self.assertNotIn("cover_pending", book)
            self.assertEqual(
                [r.method for r in requests], ["GET", "POST", "POST", "PATCH", "GET"]
            )
            tools.call.assert_not_awaited()
            self.assertEqual(tools.call_api.await_count, 2)

    async def test_browser_cover_task_resumes_with_rest_readback(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(os.environ, {"NOTION_API_TOKEN": ""}),
        ):
            root = Path(temporary)
            asset = root / "cover.png"
            asset.write_bytes(png())
            book = {
                "work_id": WORK,
                "uploaded": True,
                "cover_asset": str(asset),
                "cover_sha256": digest(png()),
            }
            state = root / "import.json"
            tools = AsyncMock()
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "awaits browser upload"):
                    await finish_cover(book, state, tools=tools)
            tools.call.assert_not_called()
            task = json.loads((root / "cover-browser.json").read_text())
            self.assertEqual(task["sha256"], digest(png()))
            tools.call_api.return_value = {
                "status": 200,
                "body": {
                    "object": "page",
                    "id": WORK,
                    "properties": {},
                    "last_edited_time": "0",
                    "cover": {
                        "type": "file",
                        "file": {"url": "https://files.example.org/cover"},
                    },
                },
            }
            client = httpx.AsyncClient
            with patch(
                "src.notion.cover.httpx.AsyncClient",
                lambda **kwargs: client(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, content=png())
                    ),
                    **kwargs,
                ),
            ):
                await verify_cover(book, state, tools=tools)
            self.assertTrue(book["cover_uploaded"])
            self.assertNotIn("cover_browser_task", book)
            await finish_cover(book, state, tools=tools)
            self.assertEqual(tools.call_api.await_count, 1)

    def test_invalid_cover_is_rejected(self):
        self.assertEqual(validate_cover(png()), "png")
        with self.assertRaises(ValueError):
            validate_cover(b"not an image")
