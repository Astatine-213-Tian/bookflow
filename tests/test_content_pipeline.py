from __future__ import annotations

import copy
import unittest

from src.content.normalize import normalize_book


class ContentPipelineTests(unittest.TestCase):
    def test_numbered_subheadings_have_no_adjacent_empty_paragraphs(self):
        from src.content.normalize import normalize_chapter

        def paragraph(text):
            return {"kind": "paragraph", "runs": [{"text": text, "styles": []}]}

        blocks = [
            paragraph("一"),
            paragraph(""),
            paragraph("正文"),
            paragraph(""),
            paragraph("\n"),
            paragraph("二"),
            paragraph(""),
            paragraph("后文"),
        ]
        result = normalize_chapter({"title": "章节", "blocks": blocks})
        self.assertEqual(
            ["".join(r["text"] for r in b["runs"]) for b in result["blocks"]],
            ["一", "正文", "二", "后文"],
        )
        self.assertEqual(result, normalize_chapter(result))

    def test_numbered_prose_items_keep_arabic_markers_and_body_format(self):
        from tests.notion_api import roundtrip

        from src.content.normalize import normalize_chapter

        blocks = [
            {"kind": "paragraph", "runs": [{"text": text, "styles": []}]}
            for text in ["１，第一项。", "继续说明。", "２，第二项。", "3、第三项。"]
        ]
        chapter = normalize_chapter({"title": "篇目", "blocks": blocks})
        actual = roundtrip(chapter["blocks"])
        self.assertEqual(
            ["".join(r["text"] for r in b["runs"]) for b in actual],
            ["1. 第一项。", "继续说明。", "2. 第二项。", "3. 第三项。"],
        )
        self.assertTrue(all(b["kind"] == "paragraph" for b in actual))
        self.assertEqual(normalize_chapter(chapter), chapter)

    def test_numbered_prose_detection_preserves_numbers_in_other_contexts(self):
        from src.content.normalize import normalize_list_markers

        blocks = [
            {"kind": "paragraph", "runs": [{"text": text, "styles": []}]}
            for text in [
                "1,000",
                "2,000",
                "3.14",
                "2012.10.07",
                "他列出 1，2，3。",
                "1，孤立数字。",
            ]
        ]
        self.assertEqual(normalize_list_markers(blocks), blocks)

    def test_numbered_subheadings_survive_source_normalization_and_notion(self):
        from tests.notion_api import roundtrip

        from src.content.normalize import normalize_chapter
        from src.inputs.html import read_html_blocks

        for markup, labels in [
            (
                "<h4>（一）开场</h4><p>正文。</p><h4>（二）后续</h4>",
                ["（一）开场", "（二）后续"],
            ),
            (
                "<h4>（1）开场</h4><p>正文。</p><h4>（2）后续</h4>",
                ["（一）开场", "（二）后续"],
            ),
            ("<p>一</p><p>正文。</p><p>二</p><p>结束。</p>", ["一", "二"]),
            ("<p>1</p><p>正文。</p><p>２</p><p>结束。</p>", ["一", "二"]),
            ("<h4>（１０）第2次尝试</h4><p>第 2 次。</p>", ["（十）第 2 次尝试"]),
            ("<h4>（一）标题（2025）</h4><p>正文。</p>", ["（一）标题（2025）"]),
        ]:
            with self.subTest(markup=markup):
                blocks = read_html_blocks(
                    f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{markup}</body></html>'.encode(),
                    "chapter.xhtml",
                    {},
                )
                chapter = normalize_chapter({"title": "篇目", "blocks": blocks})
                actual = roundtrip(chapter["blocks"])
                headings = [b for b in actual if b["kind"] == "heading"]
                self.assertEqual(
                    ["".join(r["text"] for r in b["runs"]) for b in headings], labels
                )
                self.assertTrue(
                    all(
                        b["level"] == 3 and b.get("alignment") == "center"
                        for b in headings
                    )
                )
                self.assertFalse(any(b["kind"] == "divider" for b in actual))
                self.assertEqual(normalize_chapter(chapter), chapter)

    def test_numbered_subheading_detection_requires_section_evidence(self):
        from src.content.normalize import normalize_chapter

        for blocks in [
            [{"kind": "paragraph", "runs": [{"text": "一", "styles": []}]}],
            [
                {"kind": "paragraph", "runs": [{"text": t, "styles": []}]}
                for t in ["1", "2"]
            ],
            [
                {"kind": "paragraph", "runs": [{"text": t, "styles": []}]}
                for t in ["1", "正文。", "3", "正文。"]
            ],
            [
                {"kind": "paragraph", "runs": [{"text": t, "styles": []}]}
                for t in ["2012", "正文。", "2013", "正文。"]
            ],
            [
                {"kind": "quote", "runs": [{"text": t, "styles": []}]}
                for t in ["一", "正文。", "二", "正文。"]
            ],
            [
                {
                    "kind": "paragraph",
                    "alignment": "right",
                    "runs": [{"text": t, "styles": []}],
                }
                for t in ["一", "正文。", "二", "正文。"]
            ],
            [
                {
                    "kind": "paragraph",
                    "variant": "original",
                    "runs": [{"text": t, "styles": []}],
                }
                for t in ["一", "正文。", "二", "正文。"]
            ],
        ]:
            with self.subTest(blocks=blocks):
                result = normalize_chapter({"title": "篇目", "blocks": blocks})
                self.assertFalse(any(b["kind"] == "heading" for b in result["blocks"]))

    def test_numbering_changes_preserve_rich_text_and_original_blocks(self):
        from src.content.normalize import normalize_chapter, normalize_subheadings

        original = {
            "kind": "heading",
            "level": 3,
            "variant": "original",
            "runs": [{"text": "（1）ＮＩＣＥ　ＤＯＧＳ", "styles": []}],
        }
        decimal = {
            "kind": "heading",
            "level": 3,
            "runs": [{"text": "3.14与圆周率", "styles": []}],
        }
        self.assertEqual(
            normalize_subheadings([original, decimal]), [original, decimal]
        )
        chapter = normalize_chapter(
            {
                "title": "第1章",
                "blocks": [
                    original,
                    {
                        "kind": "heading",
                        "level": 3,
                        "runs": [
                            {"text": "（1）", "styles": ["bold"]},
                            {"text": "NICE　DOGS", "styles": ["italic"]},
                        ],
                    },
                ],
            }
        )
        self.assertEqual(chapter["title"], "第1章")
        self.assertEqual(chapter["blocks"][0], original)
        self.assertEqual(
            chapter["blocks"][1]["runs"],
            [
                {"text": "（一）", "styles": ["bold"]},
                {"text": "NICE DOGS", "styles": ["italic"]},
            ],
        )

    def test_txt_preserves_volume_titles_and_scene_dividers(self):
        import tempfile
        from pathlib import Path
        from src.dataset.text import write_prepared_txt
        from tests.fixtures import prepared_crawl
        from src.content.models import Chapter, Volume

        source = prepared_crawl(
            title="书",
            author="作者",
            source_url="https://example.org",
            volumes=[
                Volume("上卷", [Chapter("第1章", ["段落。"])]),
                Volume("下卷", [Chapter("第2章", ["结尾。"])]),
            ],
        )
        source["chapters"]["chapter-1-1"]["blocks"].append(
            {"kind": "divider", "runs": []}
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "book.txt"
            write_prepared_txt(source, path)
            text = path.read_text()
        self.assertLess(text.index("上卷"), text.index("第1章"))
        self.assertLess(text.index("下卷"), text.index("第2章"))
        self.assertIn("***", text)

    def test_normalization_works_on_content_and_preserves_rich_text(self):
        source = {
            "version": 3,
            "identifier": "book-1",
            "source_format": "agent",
            "metadata": {"title": "书", "creator": "作者", "language": "zh-CN"},
            "sections": [{"member": "chapter-1"}],
            "extras": [],
            "chapters": {
                "chapter-1": {
                    "title": "第１章",
                    "role": "chapter",
                    "blocks": [
                        {"kind": "paragraph", "runs": []},
                        {
                            "kind": "paragraph",
                            "runs": [
                                {"text": "他说ＭＳＮ", "styles": ["bold"]},
                                {"text": "，ＱＱ都是１００分。", "styles": []},
                            ],
                        },
                    ],
                }
            },
        }
        original = copy.deepcopy(source)
        result, report = normalize_book(source)
        self.assertEqual(source, original)
        chapter = result["chapters"]["chapter-1"]
        self.assertEqual(chapter["title"], "第1章")
        self.assertEqual(len(chapter["blocks"]), 1)
        runs = chapter["blocks"][0]["runs"]
        self.assertEqual("".join(r["text"] for r in runs), "他说 MSN，QQ 都是 100 分。")
        self.assertIn("MSN", "".join(r["text"] for r in runs if "bold" in r["styles"]))
        self.assertEqual(normalize_book(result)[0], result)
        self.assertGreater(report["total_changes"], 0)

    def test_markdown_rules_are_bound_to_code_and_examples_execute(self):
        import hashlib
        import json
        import re
        from pathlib import Path

        from src.content.normalize import (
            RULES_SHA256,
            normalize_chapter,
            normalize_text,
        )
        from src.content.titles import normalize_volume_title

        document = (
            Path(__file__).resolve().parents[1] / "docs/normalization.md"
        ).read_bytes()
        self.assertEqual(hashlib.sha256(document).hexdigest(), RULES_SHA256)
        examples = json.loads(
            re.search(
                r"```normalization-examples\n(.*?)\n```", document.decode(), re.S
            )[1]
        )
        for example in examples:
            with self.subTest(example=example):
                actual = normalize_text(
                    example["input"], title=example.get("title", False)
                )
                self.assertEqual(actual, example["expected"])
                self.assertEqual(
                    normalize_text(actual, title=example.get("title", False)), actual
                )
        block_examples = json.loads(
            re.search(
                r"```normalization-block-examples\n(.*?)\n```", document.decode(), re.S
            )[1]
        )
        for example in block_examples:
            with self.subTest(example=example):
                actual = normalize_chapter(
                    {"title": "篇目", "blocks": example["input"]}
                )
                self.assertEqual(actual["blocks"], example["expected"])
                self.assertEqual(normalize_chapter(actual), actual)
        for example in json.loads(
            re.search(
                r"```normalization-volume-examples\n(.*?)\n```", document.decode(), re.S
            )[1]
        ):
            with self.subTest(volume=example):
                actual = normalize_volume_title(example["input"])
                self.assertEqual(actual, example["expected"])
                self.assertEqual(normalize_volume_title(actual), actual)

    def test_all_destinations_receive_the_same_cleaned_body(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from src.content.models import Chapter, Volume
        from src.crawler.models import CrawledBook
        from src.inputs.epub import read_epub_source
        from src.workflows.ingest import OutputOptions, write_outputs

        source = CrawledBook(
            "书",
            "作者",
            [Volume("", [Chapter("第１章", ["", "ＭＳＮ，ＱＱ", "重复。", "重复。"])])],
            "https://example.test/book",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "src.notion.upload.upload_source", return_value=root / "state.json"
            ) as upload:
                write_outputs(
                    source,
                    OutputOptions(
                        output=root / "book.epub",
                        txt_output=root / "book.txt",
                        output_formats=("epub", "txt", "notion"),
                    ),
                )
            expected = ["MSN，QQ", "重复。", "重复。"]

            def text(book):
                return [
                    "".join(r["text"] for r in b["runs"])
                    for b in next(iter(book["chapters"].values()))["blocks"]
                ]

            self.assertEqual(text(upload.call_args.args[0]), expected)
            self.assertEqual(
                text(read_epub_source(root / "book.epub").source), expected
            )
            self.assertTrue(
                (root / "book.txt").read_text().endswith("MSN，QQ\n重复。\n重复。\n")
            )

    def test_metadata_lookup_fills_missing_values_without_erasing_explicit_values(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from src.content.contract import metadata_defaults
        from src.metadata.enrich import enrich_source

        metadata = metadata_defaults(
            {
                "title": "User title",
                "creator": "User author",
                "date": "2008-01-01",
                "subjects": ["danmei"],
            }
        )
        found = SimpleNamespace(
            title="Remote title",
            language="zh-CN",
            date="2019-01-01",
            source="https://example.test",
            description="Remote description",
            subjects=["remote"],
            series_verified=False,
            provider="fixture",
            table_of_contents=None,
            table_of_contents_error=None,
        )
        value = {"metadata": metadata}
        enrich_source(value, lookup=Mock(find=Mock(return_value=found)))
        self.assertEqual(value["metadata"]["title"], "User title")
        self.assertEqual(value["metadata"]["creator"], "User author")
        self.assertEqual(value["metadata"]["date"], "2008-01-01")
        self.assertEqual(value["metadata"]["subjects"], ["danmei"])
        self.assertEqual(value["metadata"]["description"], "Remote description")

    def test_original_bilingual_blocks_are_not_rewritten(self):
        from src.content.normalize import normalize_chapter

        block = {
            "kind": "paragraph",
            "runs": [{"text": '"Exact English,"  unchanged.', "styles": ["italic"]}],
            "language": "en",
            "variant": "original",
        }
        result = normalize_chapter({"title": "第1章", "blocks": [block]})
        self.assertEqual(result["blocks"], [block])
