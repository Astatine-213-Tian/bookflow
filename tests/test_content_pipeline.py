from __future__ import annotations

import copy
import unittest

from src.content.normalize import normalize_book


class ContentPipelineTests(unittest.TestCase):
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

        from src.content.normalize import RULES_SHA256, normalize_text

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
