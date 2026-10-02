from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from src.cli.ingest import main as ingest_main
from src.cli.notion_book import run as notion_main
from src.content.blocks import content_signature
from src.content.edition_outline import apply_edition_layout, apply_jjwxc_outline
from src.content.models import Chapter, Volume
from src.content.prepare import prepare_crawl
from src.content.prepared import load_prepared_source
from src.content.text_source import read_txt_source
from src.dataset.text import write_prepared_txt
from src.epub.source import read_epub_source
from src.epub.writer import export_local
from src.metadata.catalog import MetadataEnrichmentReport
from src.metadata.jjwxc import JjwxcChapter, JjwxcContents, JjwxcVolume
from src.runtime.files import digest
from src.workflows.ingest import IngestResult
from src.workflows.edition_comparison import compare_editions
from src.workflows.local import prepare_local


def source():
    book = prepare_crawl(
        title="合成书",
        author="测试作者",
        source_url="https://example.test/book",
        volumes=[
            Volume(
                "开端",
                [Chapter("第1章 起点", ["重复台词。", "重复台词。", "第一段。"])],
            ),
            Volume("尾声 春归", [Chapter("第2章 回家", ["结束。"])]),
            Volume("番外", [Chapter("番外", ["补充。"])]),
        ],
    )
    book["identifier"] = "fixture"
    return book


class LocalImportTests(unittest.TestCase):
    def test_reviewed_layout_splits_afterword_from_extra_and_preserves_content(self):
        book = source()
        member = list(book["chapters"])[-1]
        original = copy.deepcopy(book["chapters"][member])
        original["blocks"] += copy.deepcopy(original["blocks"])
        book["chapters"][member] = original
        layout = {
            member: {
                "expected_title": original["title"],
                "parts": [
                    {"start": 0, "stop": 1, "role": "afterword", "title": "后记"},
                    {"start": 1, "stop": 2, "role": "extra", "title": "补篇"},
                ],
            }
        }
        report = apply_edition_layout(book, layout)
        self.assertEqual(
            book["chapters"][member]["blocks"] + book["extras"][0]["blocks"],
            original["blocks"],
        )
        self.assertEqual([x["title"] for x in book["extras"]], ["补篇", "番外"])
        self.assertEqual(len(report), 2)
        aligned = apply_jjwxc_outline(
            book,
            {
                "volumes": [
                    {"title": "开端", "chapters": [{"number": 1, "title": "起点"}]}
                ]
            },
        )
        self.assertEqual(aligned["aligned_main_chapters"], 1)
        self.assertEqual(book["sections"][-1], {"member": member})

    def test_reviewed_layout_rejects_stale_titles_and_gaps_without_mutation(self):
        original = source()
        member = next(iter(original["chapters"]))
        for title, start, stop in [
            ("stale", 0, 3),
            ("第1章 起点", 1, 3),
            ("第1章 起点", 0, 2),
        ]:
            with self.subTest(title=title, start=start, stop=stop):
                book = copy.deepcopy(original)
                with self.assertRaises(ValueError):
                    apply_edition_layout(
                        book,
                        {
                            member: {
                                "expected_title": title,
                                "parts": [
                                    {
                                        "start": start,
                                        "stop": stop,
                                        "role": "extra",
                                        "title": "补篇",
                                    }
                                ],
                            }
                        },
                    )
                self.assertEqual(book, original)

    def test_layout_preparation_persists_and_rejects_changed_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "edition.epub"
            book = source()
            member = list(book["chapters"])[-1]
            export_local(book, path)
            layout = {
                member: {
                    "expected_title": book["chapters"][member]["title"],
                    "parts": [
                        {"start": 0, "stop": 1, "role": "afterword", "title": "后记"}
                    ],
                }
            }
            with patch(
                "src.epub.maintenance.enrich_epub_metadata",
                return_value=MetadataEnrichmentReport(
                    path=path, applied=False, status="unmatched"
                ),
            ):
                prepared, _, _ = prepare_local(
                    path, root / "run", chapter_layout=layout, use_jjwxc_outline=False
                )
            self.assertEqual(prepared["chapters"][member]["title"], "后记")
            self.assertEqual(prepared["layout_report"][0]["role"], "afterword")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                prepare_local(path, root / "run", use_jjwxc_outline=False)

    def test_prepared_txt_retains_extra_and_repeat_when_read_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "book.txt"
            write_prepared_txt(source(), path)
            parsed = read_txt_source(path)
            self.assertEqual(len(parsed["extras"]), 1)
            self.assertEqual(
                parsed["extras"][0]["blocks"][0]["runs"][0]["text"], "补充。"
            )
            paragraphs = parsed["chapters"]["EPUB/chap_01_001.xhtml"]["blocks"]
            self.assertEqual(paragraphs[0], paragraphs[1])

    def test_prepared_cover_asset_is_loaded_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = source()
            value["assets"] = {
                "cover": {
                    "path": "cover.jpg",
                    "mime": "image/jpeg",
                    "sha256": digest(b"image"),
                }
            }
            path = root / "source.json"
            path.write_text(json.dumps(value))
            (root / "cover.jpg").write_bytes(b"image")
            self.assertEqual(load_prepared_source(path)[1], b"image")
            (root / "cover.jpg").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "cover asset changed"):
                load_prepared_source(path)

    def test_epub_import_preserves_outline_extra_and_repeated_paragraphs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edition.epub"
            before = source()
            export_local(before, path)
            after = read_epub_source(path).source
            self.assertEqual(after["sections"], before["sections"])
            self.assertEqual(after["extras"], before["extras"])
            for member, chapter in before["chapters"].items():
                self.assertEqual(
                    content_signature(after["chapters"][member]["blocks"]),
                    content_signature(chapter["blocks"]),
                )

    def test_comparison_detects_missing_repeated_paragraph_and_unique_versions(self):
        from src.dataset.library import extract_epub_text

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            epub = root / "edition.epub"
            txt = root / "edition.txt"
            book = source()
            book["extras"] = []
            export_local(book, epub)
            txt.write_text(extract_epub_text(epub)[2])
            report = compare_editions(epub, txt)
            self.assertEqual(report["selected"], str(epub))
            self.assertEqual(report["differences"][0]["left_excerpt"], ["重复台词。"])
            txt.write_text(txt.read_text().replace("结束。", "独有的新段落。"))
            self.assertIsNone(compare_editions(epub, txt)["selected"])

    def test_comparison_preserves_english_word_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = root / "left.txt", root / "right.txt"
            left.write_text("合成书\n作者：测试作者\n\n第1章 起点\na part\n")
            right.write_text(left.read_text().replace("a part", "apart"))
            self.assertIsNone(compare_editions(left, right)["selected"])

    def test_directory_uses_arbitrary_group_names_and_explicit_aliases(self):
        book = source()
        original = copy.deepcopy(book["chapters"])
        contents = {
            "volumes": [
                {"title": "一朵云", "chapters": [{"number": 1, "title": "新起点"}]},
                {"title": "尾声：春归", "chapters": [{"number": 2, "title": "回家"}]},
            ]
        }
        with self.assertRaisesRegex(ValueError, "Edition title differs"):
            apply_jjwxc_outline(book, contents)
        report = apply_jjwxc_outline(book, contents, aliases={"第1章 起点": "新起点"})
        self.assertEqual(
            [n["title"] for n in book["sections"]], ["一朵云", "尾声·春归"]
        )
        self.assertEqual(book["chapters"], original)
        self.assertEqual(report["aligned_main_chapters"], 2)

    def test_directory_accepts_identical_number_only_chapter_titles(self):
        book = source()
        for number, chapter in enumerate(book["chapters"].values(), 1):
            chapter["title"] = f"第{number}章"
        contents = {
            "volumes": [
                {
                    "title": "",
                    "chapters": [
                        {"number": 1, "title": "第1章"},
                        {"number": 2, "title": "第2章"},
                    ],
                }
            ]
        }
        report = apply_jjwxc_outline(book, contents)
        self.assertEqual(report["title_differences"], [])
        self.assertEqual(report["aligned_main_chapters"], 2)

    def test_preparation_is_reusable_preserves_original_and_rejects_changed_inputs(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "edition.epub"
            export_local(source(), path)
            before = digest(path.read_bytes())
            with patch(
                "src.epub.maintenance.enrich_epub_metadata",
                return_value=MetadataEnrichmentReport(
                    path=path, applied=False, status="unmatched"
                ),
            ):
                first, _, _ = prepare_local(path, root / "run", use_jjwxc_outline=False)
            with patch(
                "src.workflows.local.normalize_new_epub",
                side_effect=AssertionError("repeated preparation"),
            ):
                second, _, _ = prepare_local(
                    path, root / "run", use_jjwxc_outline=False
                )
            self.assertEqual(first, second)
            self.assertEqual(digest(path.read_bytes()), before)
            self.assertEqual(
                json.loads((root / "run/second_pass.json").read_text())[
                    "total_changes"
                ],
                0,
            )
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                prepare_local(path, root / "run", use_jjwxc_outline=True)

    def test_local_cli_bypasses_provider_and_passes_reviewed_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edition.epub"
            path.write_bytes(b"fixture")
            with (
                patch(
                    "src.cli.ingest.find_parser",
                    side_effect=AssertionError("provider called"),
                ),
                patch(
                    "src.workflows.local.ingest_local", return_value=IngestResult()
                ) as run,
            ):
                self.assertEqual(
                    ingest_main([str(path), "--mode", "notion", "--keep-outline"]), 0
                )
            self.assertFalse(run.call_args.kwargs["use_jjwxc_outline"])

    def test_reviewed_aliases_resume_incomplete_preparation_in_the_same_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "edition.epub"
            export_local(source(), path)
            contents = JjwxcContents(
                "https://example.test/book",
                (
                    JjwxcVolume(
                        "始末",
                        (
                            JjwxcChapter(1, "新起点", None),
                            JjwxcChapter(2, "回家", None),
                        ),
                    ),
                ),
            )
            metadata = MetadataEnrichmentReport(
                path=path, applied=False, status="fixture", table_of_contents=contents
            )
            with patch(
                "src.epub.maintenance.enrich_epub_metadata", return_value=metadata
            ):
                with self.assertRaisesRegex(ValueError, "outline_review.json"):
                    prepare_local(path, root / "run")
                aliases = json.loads(
                    (root / "run/chapter_aliases.proposed.json").read_text()
                )
                self.assertEqual(aliases, {"第1章 起点": "新起点"})
                result, _, _ = prepare_local(
                    path, root / "run", chapter_aliases=aliases
                )
            self.assertEqual(result["sections"][0]["title"], "始末")
            self.assertEqual(
                result["chapters"]["EPUB/chap_01_001.xhtml"]["title"], "第1章 起点"
            )

    def test_notion_upload_cli_calls_existing_uploader(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.json"
            path.write_text(json.dumps(source()))
            with patch(
                "src.cli.notion_book.upload_source",
                return_value=Path("checkpoint.json"),
            ) as upload:
                notion_main(
                    [
                        "upload",
                        "--source",
                        str(path),
                        "--cover-url",
                        "https://example.test/cover.jpg",
                    ]
                )
            self.assertEqual(upload.call_args.args[0], source())
            self.assertEqual(
                upload.call_args.kwargs["cover_url"], "https://example.test/cover.jpg"
            )

    def test_unlisted_spine_content_is_never_silently_omitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edition.epub"
            export_local(source(), path)
            with ZipFile(path) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            files["EPUB/nav.xhtml"] = files["EPUB/nav.xhtml"].replace(
                b'<li><a href="extra_001.xhtml">', b'<li><a href="chap_01_001.xhtml">'
            )
            # Replace the link independently of serializer whitespace.
            files["EPUB/nav.xhtml"] = files["EPUB/nav.xhtml"].replace(
                b'href="extra_001.xhtml"', b'href="chap_01_001.xhtml"'
            )
            with ZipFile(path, "w") as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            with self.assertRaises(ValueError):
                read_epub_source(path)


if __name__ == "__main__":
    unittest.main()
