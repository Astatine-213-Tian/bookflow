from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from src.content.blocks import block_text
from src.content.changes import apply_changes, content_hash
from src.content.normalization import NormalizationReport
from src.content.normalize import normalize_book, normalize_chapter
from src.content.titles import normalize_volume_title
from src.epub.cleanup import normalize_member
from src.epub.normalize import normalize_epub
from src.epub.writer import export_local
from src.notion.cms import chapter_entries
from tests.fixtures import paragraph, write_source


class NormalizationRulesTests(unittest.TestCase):
    def test_volume_number_scope_and_idempotence(self):
        cases = {
            "卷１　初识": "卷一·初识",
            "第 12 卷：重逢": "卷十二·重逢",
            "卷一—初识": "卷一·初识",
            "卷一\u2003初识": "卷一·初识",
            "卷1-初识": "卷一·初识",
            "卷一百零二 重逢": "卷一百零二·重逢",
            "卷一百零二重逢": "卷一百零二重逢",
            "卷一万物复苏": "卷一万物复苏",
            "第一卷 万物复苏": "卷一·万物复苏",
            "卷一〇二 重逢": "卷一百零二·重逢",
            "第一万卷 未来": "卷一万·未来",
            "第10010卷 未来": "卷一万零一十·未来",
            "第10011卷 未来": "卷一万零一十一·未来",
            "卷001": "卷一",
            "卷1.5": "卷1.5",
            "卷1··  重逢": "卷一·重逢",
            "卷1·": "卷一",
            "中卷": "中卷",
            "续卷 新的 开始": "续卷·新的·开始",
            "终卷 末页": "终卷·末页",
            "风起": "风起",
            "正文 上（2008）": "正文·上（2008）",
            "2015 年续篇": "2015·年续篇",
            "第二部 风云": "第二部·风云",
            "序卷": "序卷",
            "卷外篇": "卷外篇",
            "书卷人生": "书卷人生",
        }
        for before, expected in cases.items():
            with self.subTest(before=before):
                result = normalize_volume_title(before)
                self.assertEqual(result, expected)
                report = NormalizationReport(Path("content"), True)
                self.assertEqual(
                    normalize_volume_title(result, report=report), expected
                )
                self.assertEqual(report.total_changes, 0)

        report = NormalizationReport(Path("content"), True)
        self.assertEqual(
            normalize_volume_title("卷一万物复苏", report=report), "卷一万物复苏"
        )
        self.assertEqual(report.issues[0].kind, "ambiguous_volume_number")

    def test_shared_volume_labels_preserve_identity_body_and_color(self):
        with tempfile.TemporaryDirectory() as d:
            source = write_source(
                Path(d), ["我读过第一卷。"], chapter_title="第1章 初识"
            )
            source["sections"] = [
                {
                    "id": "volume-one",
                    "title": "第一卷 初识",
                    "children": [{"member": "01"}],
                }
            ]
            source["volume_colors"] = {"第一卷 初识": "blue"}
            before = copy.deepcopy(source)
            prepared, _ = normalize_book(source)
            self.assertEqual(source, before)
            self.assertEqual(prepared["chapters"], before["chapters"])
            self.assertEqual(prepared["sections"][0]["id"], "volume-one")
            self.assertEqual(prepared["volume_colors"], {"卷一·初识": "blue"})
            self.assertEqual(chapter_entries(prepared), [("01", "卷一·初识")])
            self.assertEqual(normalize_book(prepared)[0], prepared)
            prepared["volume_colors"]["第一卷 初识"] = "red"
            with self.assertRaisesRegex(ValueError, "colors conflict"):
                normalize_book(prepared)

    def test_explicit_outline_edit_uses_same_volume_rule(self):
        with tempfile.TemporaryDirectory() as d:
            source = write_source(Path(d), ["正文"])
            source["volume_colors"] = {"卷一 初识": "blue"}
            request = {
                "version": 1,
                "id": "layout",
                "book_id": source["identifier"],
                "operations": [
                    {
                        "kind": "set_outline",
                        "expected_sha256": content_hash(source["sections"]),
                        "sections": [
                            {
                                "id": "v1",
                                "title": "卷一 初识",
                                "children": source["sections"],
                            }
                        ],
                    }
                ],
            }
            result, _ = apply_changes(source, request)
            self.assertEqual(result["sections"][0]["title"], "卷一·初识")
            self.assertEqual(result["volume_colors"], {"卷一·初识": "blue"})
            self.assertEqual(result["chapters"], source["chapters"])

    def test_archive_volume_repair_uses_parent_structure_and_preserves_inline(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = write_source(root, ["我读过第一卷。"])
            source["sections"] = [
                {"title": "第一卷 新的 世界", "children": source["sections"]}
            ]
            path = root / "book.epub"
            export_local(source, path)
            with ZipFile(path) as archive:
                files = [(i, archive.read(i.filename)) for i in archive.infolist()]
            with ZipFile(path, "w") as archive:
                for info, data in files:
                    if info.filename == "EPUB/nav.xhtml":
                        data = data.replace(
                            "第一卷".encode(), "第<strong>一</strong>卷".encode()
                        )
                    archive.writestr(info, data)
            report = normalize_epub(path)
            self.assertGreater(report.change_counts["volume_title_normalized"], 0)
            with ZipFile(path) as archive:
                nav = ET.fromstring(archive.read("EPUB/nav.xhtml"))
                ncx = ET.fromstring(archive.read("EPUB/toc.ncx"))
                self.assertEqual(
                    "".join(nav.find(".//{*}a").itertext()), "卷一·新的·世界"
                )
                self.assertIsNotNone(nav.find(".//{*}strong"))
                self.assertEqual(
                    ncx.findtext(".//{*}navLabel/{*}text"), "卷一·新的·世界"
                )
                body = ET.fromstring(archive.read("EPUB/chapter_0001.xhtml"))
                self.assertEqual(body.findtext(".//{*}p"), "我读过第一卷。")
            self.assertEqual(normalize_epub(path, apply=False).total_changes, 0)

    def test_structural_cleanup_preserves_anchors_and_aligned_original(self):
        blocks = [
            paragraph(""),
            paragraph("前文，"),
            paragraph("注释作者有话说：内容"),
            paragraph("后文"),
        ]
        blocks[0]["anchor"] = "start"
        blocks[2].update(anchor="note", footnote="note")
        chapter = normalize_chapter({"title": "篇目", "blocks": blocks})
        self.assertEqual(len(chapter["blocks"]), 4)
        self.assertEqual(
            [b.get("anchor") for b in chapter["blocks"]], ["start", None, "note", None]
        )
        original = {
            "title": "篇目",
            "blocks": [
                {**paragraph(""), "variant": "original"},
                {
                    "kind": "heading",
                    "level": 3,
                    "variant": "original",
                    "runs": [{"text": "1", "styles": []}],
                },
            ],
        }
        self.assertEqual(normalize_chapter(original), original)

    def test_removed_subheading_gaps_are_reported(self):
        report = NormalizationReport(Path("content"), True)
        chapter = normalize_chapter(
            {
                "title": "篇目",
                "blocks": [
                    paragraph("前文"),
                    paragraph(""),
                    {
                        "kind": "heading",
                        "level": 3,
                        "runs": [{"text": "（1）", "styles": []}],
                    },
                    paragraph(""),
                    paragraph("正文"),
                ],
            },
            report=report,
        )
        self.assertEqual(
            [block_text(b) for b in chapter["blocks"]], ["前文", "（一）", "正文"]
        )
        self.assertEqual(report.change_counts["subheading_empty_removed"], 2)

    def test_archive_structural_edits_preserve_references_and_alignment(self):
        cases = [
            '<p id="a">前文作者有话说：后文</p>',
            '<p id="a">前文，</p><p id="b">后文。</p>',
            '<p>前文，</p><p><a name="b"/>后文。</p>',
            '<p>前文</p><p id="b">”</p>',
            '<p class="zh-translation">前文</p><p class="zh-translation">”</p>',
            '<p data-variant="translation">前文作者有话说：后文</p>',
            '<aside epub:type="footnote"><p>前文，</p><p>后文。</p></aside>',
            '<p style="text-align: center">前文，</p><p>后文。</p>',
            '<p data-variant="original">ＭＳＮ　ＤＯＧＳ！</p>',
        ]
        for body in cases:
            with self.subTest(body=body):
                data = (
                    '<html xmlns:epub="http://www.idpf.org/2007/ops">'
                    f"<head/><body>{body}</body></html>"
                ).encode()
                result = normalize_member(
                    "chapter.xhtml", data,
                    NormalizationReport(Path("content"), True),
                    grouped_fanwai_titles=set(),
                )
                self.assertEqual(result, data)


if __name__ == "__main__":
    unittest.main()
