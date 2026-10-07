from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lxml import etree as ET
from notion_books import NotionBooks, text_blocks
from tests.notion_api import BlockAPI, PAGE, SOURCE, paragraphs, roundtrip

from src.content.blocks import content_signature
from src.content.models import Chapter, Volume
from src.content.normalize import normalize_chapter
from src.crawler.models import CrawledBook
from src.epub.archive import install_archive
from src.epub.writer import create_book
from src.inputs.html import read_html_blocks
from src.notion.upload import upload_row
from src.runtime.files import digest
from src.workflows.ingest import OutputOptions, write_outputs
from tests.fixtures import isolated_workdir, prepared_crawl as prepare_crawl


class SourceTests(unittest.TestCase):
    def setUp(self):
        isolated_workdir(self)

    def test_numbered_prose_survives_native_paragraph_readback(self):
        blocks = roundtrip(paragraphs("1. 第一项。\n\n2. 第二项。"))
        self.assertEqual(text_blocks(blocks), ["1. 第一项。", "", "2. 第二项。"])
        self.assertTrue(all(b["kind"] == "paragraph" for b in blocks))

    def test_source_whitespace_becomes_paragraph_layout_and_explicit_line_breaks(self):
        data = '<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>标题</h2><p> A sentence.\u2028</p><p> </p></body></html>'.encode()
        blocks = normalize_chapter(
            {"title": "标题", "blocks": read_html_blocks(data, "chapter.xhtml", {})[1:]}
        )["blocks"]
        self.assertEqual(text_blocks(blocks), ["A sentence.\n", ""])
        self.assertEqual(
            content_signature(roundtrip(blocks)),
            content_signature(blocks),
        )

    def test_links_preserve_labels_and_unlinked_url_text(self):
        url = "https://example.org/book?id=1"
        blocks = paragraphs(url)
        blocks.append(
            {
                "kind": "paragraph",
                "runs": [{"text": "Different label", "styles": [], "href": url}],
            }
        )
        actual = roundtrip(blocks)
        self.assertEqual(content_signature(actual), content_signature(blocks))
        self.assertNotIn("href", actual[0]["runs"][0])

    def test_install_checks_observed_bytes_and_backs_up_absolute_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            candidate, target = folder / "candidate.epub", folder / "target.epub"
            candidate.write_bytes(b"replacement")
            target.write_bytes(b"original")
            with patch("src.epub.archive.DEFAULT_BACKUP_DIR", folder / "backups"):
                with self.assertRaisesRegex(ValueError, "changed"):
                    install_archive(candidate, target, digest(b"outdated"))
                self.assertEqual(target.read_bytes(), b"original")
                backup = install_archive(candidate, target, digest(b"original"))
                self.assertEqual(backup.read_bytes(), b"original")
                self.assertEqual(target.read_bytes(), candidate.read_bytes())
                new_target = folder / "new" / "book.epub"
                self.assertIsNone(install_archive(candidate, new_target, None))
                self.assertEqual(new_target.read_bytes(), candidate.read_bytes())

    def test_crawl_prepares_explicit_layout_and_export_does_not_interpret_words(self):
        source = prepare_crawl(
            title="书",
            author="作者",
            source_url="https://example.org/book",
            volumes=[
                Volume("卷一", [Chapter("第1章 开始", ["普通段落。", "***", "全文完"])])
            ],
            intro_paragraphs=["简介内容。"],
        )
        source["identifier"] = "fixture-source"
        chapter = source["chapters"]["chapter-1-1"]
        self.assertEqual(chapter["blocks"][1]["alignment"], "center")
        # The presentation layer must obey changed layout even for marker words.
        chapter["blocks"][-1].pop("alignment", None)
        chapter["blocks"].append(
            {
                "kind": "heading",
                "level": 3,
                "runs": [{"text": "任意内容", "styles": []}],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.epub"
            create_book(source, path)
            with zipfile.ZipFile(path) as archive:
                blocks = read_html_blocks(
                    archive.read("EPUB/chapter_0002.xhtml"),
                    "EPUB/chapter_0002.xhtml",
                    {n: archive.read(n) for n in archive.namelist()},
                )[1:]
                self.assertEqual(
                    content_signature(blocks), content_signature(chapter["blocks"])
                )
                root = ET.fromstring(archive.read("EPUB/chapter_0002.xhtml"))
                self.assertIn("font-size: 1.1em", root.find(".//{*}h3").get("style"))

    def test_italic_whitespace_and_unicode_line_separator_preserve_prose(self):
        blocks = [
            {
                "kind": "paragraph",
                "runs": [
                    {"text": " A thought. ", "styles": ["italic"]},
                    {"text": "More\u2028words", "styles": []},
                ],
            }
        ]
        actual = roundtrip(blocks)
        self.assertEqual(content_signature(actual), content_signature(blocks))
        self.assertEqual(text_blocks(actual), [" A thought. More\u2028words"])

    def test_selected_notion_output_publishes_without_building_an_epub(self):
        with (
            patch(
                "src.notion.upload.upload_source",
                return_value=Path("source.json"),
            ) as publish_source,
            patch("src.workflows.prepare.enrich_source", return_value={}),
        ):
            result = write_outputs(
                CrawledBook(
                    title="书",
                    author="作者",
                    volumes=[Volume("", [Chapter("第1章", ["内容"])])],
                    source_url="https://example.org/book",
                ),
                OutputOptions(output_formats=("notion",)),
            )
        self.assertEqual(result.notion_state, Path("source.json"))
        self.assertNotIn("output", publish_source.call_args.kwargs)

    def test_right_alignment_uses_one_occupied_column_and_rejects_multiple(self):
        blocks = [
            {
                "kind": "paragraph",
                "alignment": "right",
                "runs": [{"text": "署名", "styles": []}],
            }
        ]
        self.assertEqual(
            content_signature(roundtrip(blocks)), content_signature(blocks)
        )


class BatchResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_preserves_numbered_prose_and_checkpoint_identity(self):
        book = prepare_crawl(
            title="Fixture",
            author="Author",
            source_url="https://example.org/book",
            volumes=[Volume("", [Chapter("Chapter", ["1，第一项。", "2，第二项。"])])],
        )
        member, item = next(iter(book["chapters"].items()))
        api = BlockAPI()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "import.json"
            await upload_row(
                item,
                book,
                state,
                data_source=SOURCE,
                properties={"章节": "Chapter"},
                title_property="章节",
                tools=api,
            )
            saved = json.loads(state.read_text())["chapters"][member]
            self.assertTrue(saved["verified"])
            mutations = api.mutations
            await upload_row(
                item,
                book,
                state,
                data_source=SOURCE,
                properties={"章节": "Chapter"},
                title_property="章节",
                tools=api,
            )
            self.assertEqual(api.mutations, mutations)
            doc = await NotionBooks(api=api).document(saved["page_id"])
            self.assertEqual(text_blocks(doc.blocks), ["1. 第一项。", "2. 第二项。"])

    async def test_title_only_source_page_is_readable(self):
        api = BlockAPI()
        document = await NotionBooks(api=api).document(PAGE)
        self.assertEqual(document.properties["章节"], "Example")
        self.assertEqual(document.blocks, [])
