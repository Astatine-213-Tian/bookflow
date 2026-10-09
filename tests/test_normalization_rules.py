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
from src.content.normalize import (
    normalize_book, normalize_chapter, normalize_marker_block, normalize_text,
)
from src.content.titles import normalize_volume_title
from src.epub.cleanup import normalize_member
from src.epub.normalize import normalize_epub
from src.epub.writer import export_local
from src.notion.cms import chapter_entries
from tests.fixtures import paragraph, write_source


class NormalizationRulesTests(unittest.TestCase):
    def test_chapter_ordinals_use_chinese_without_renumbering(self):
        cases = {
            "第 ００１ 章 标题2012": "第一章 标题 2012",
            "第0回": "第零回",
            "第85章": "第八十五章",
            "第94-95章": "第九十四-九十五章",
            "第102节 Part 2": "第一百零二节 Part 2",
            "第10001章": "第一万零一章",
            "第１回 路西斐尔书（一）": "第一回 路西斐尔书（一）",
            "第一〇二章": "第一百零二章",
            "Part 1": "Part 1",
            "我读过第1章": "我读过第1章",
            "第1章 番外1 旅途": "番外一·旅途",
        }
        for before, after in cases.items():
            with self.subTest(before=before):
                self.assertEqual(normalize_text(before, title=True), after)
                report = NormalizationReport(Path("content"), True)
                self.assertEqual(normalize_text(after, title=True, report=report), after)
                self.assertEqual(report.total_changes, 0)

    def test_chapter_ordinal_spanning_epub_inline_markup_preserves_identity(self):
        source = (
            '<html><body><h2 id="chapter">第<b>１２</b>章 标题 2012</h2>'
            '<p data-variant="original">第12章</p></body></html>'
        ).encode()
        report = NormalizationReport(Path("book.epub"), True)
        result = normalize_member(
            "chapter.xhtml", source, report=report, grouped_fanwai_titles=set()
        )
        root = ET.fromstring(result)
        heading = root.find("body/h2")
        self.assertEqual("".join(heading.itertext()), "第十二章 标题 2012")
        self.assertEqual(heading.attrib["id"], "chapter")
        self.assertIsNotNone(heading.find("b"))
        self.assertEqual(root.findtext("body/p"), "第12章")
        self.assertEqual(
            normalize_member(
                "chapter.xhtml", result, report=report, grouped_fanwai_titles=set()
            ), result
        )

    def test_standalone_endings_center_once_and_keep_words_and_styles(self):
        cases = {
            "全文完": "——全文完——",
            "本卷完": "——本卷完——",
            "第三部完": "——第三部·完——",
            "--书名终--": "——书名·终——",
            "END": "——END——",
            "The End": "——The End——",
            "The End of Book of Lucifel": "——The End of Book of Lucifel——",
            "The End of Book Belial": "——The End of Book Belial——",
            "The end of Part1.": "——The end of Part1.——",
            "————The end of book of Lucifer————": "——The end of book of Lucifer——",
        }
        for before, expected in cases.items():
            for kind in ("paragraph", "heading"):
                with self.subTest(before=before, kind=kind):
                    block = paragraph(before)
                    block.update(kind=kind, anchor="ending", alignment="right")
                    if kind == "heading":
                        block["level"] = 3
                    block["runs"][0]["styles"] = ["italic"]
                    block["runs"][0]["href"] = "https://example.org/book"
                    result = normalize_chapter({"title": "END", "blocks": [block]})
                    actual = result["blocks"][0]
                    self.assertEqual(result["title"], "END")
                    self.assertEqual(block_text(actual), expected)
                    self.assertEqual(actual["kind"], kind)
                    self.assertEqual(actual["alignment"], "center")
                    self.assertEqual(actual["anchor"], "ending")
                    self.assertTrue(all(r["styles"] == ["italic"] for r in actual["runs"]))
                    self.assertTrue(all(r["href"] == "https://example.org/book" for r in actual["runs"]))
                    report = NormalizationReport(Path("content"), True)
                    self.assertEqual(normalize_chapter(result, report=report), result)
                    self.assertEqual(report.total_changes, 0)
        bold = paragraph("The End")
        bold["runs"][0]["styles"] = ["bold"]
        self.assertEqual(
            normalize_chapter({"title": "篇目", "blocks": [bold]})["blocks"][0]["kind"],
            "paragraph",
        )

    def test_marker_scope_does_not_swallow_prose_or_reference_text(self):
        for text in ("他终于说完", "第三部还没写完", "永无终结。", "The end of the world is near.",
                     "The end of the book was sad.", "The end of Part 1 was surprising.",
                     "We reached the end.", "甲——乙", "--普通分隔标题--", "--", "***"):
            block = paragraph(text)
            self.assertEqual(normalize_marker_block(block), block)
        for text in ("----", "The End"):
            block = {**paragraph(text), "variant": "original"}
            self.assertEqual(normalize_marker_block(block), block)
        for protected in ({"footnote": "note"}, {"runs": [{"text": "----", "styles": [], "href": "#note"}]}):
            block = {**paragraph("----"), **protected}
            self.assertEqual(normalize_marker_block(block), block)

    def test_dash_lines_become_dividers_and_keep_anchors(self):
        from notion_books import content_matches
        from tests.notion_api import roundtrip

        blocks = [
            {**paragraph(line), "anchor": f"rule-{i}", "alignment": "center"}
            for i, line in enumerate(("---", "------------", "————", "－ － －", "– – –"))
        ]
        result = normalize_chapter({"title": "篇目", "blocks": blocks})
        self.assertEqual(result["blocks"], [
            {"kind": "divider", "runs": [], "anchor": f"rule-{i}"} for i in range(5)
        ])
        self.assertEqual(normalize_chapter(result), result)
        self.assertTrue(content_matches(roundtrip(result["blocks"]), result["blocks"], {}))

    def test_archive_marker_cleanup_preserves_inline_and_rule_identity(self):
        raw = (
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<p id="rule"><em>------</em></p>'
            '<p id="end" style="text-align: right; text-indent: 2em;">'
            'The End of <em>Book of Lucifel</em></p>'
            '<h3>全文完</h3><p>甲——乙</p>'
            '<p data-variant="original">The End</p>'
            '<p><a href="#end">----</a></p>'
            '</body></html>'
        ).encode()
        report = NormalizationReport(Path("fixture.epub"), True)
        result = normalize_member("chapter.xhtml", raw, report, grouped_fanwai_titles=set())
        body = ET.fromstring(result).find("{*}body")
        self.assertEqual(body[0].tag.rsplit("}", 1)[-1], "hr")
        self.assertEqual(body[0].get("id"), "rule")
        self.assertEqual("".join(body[1].itertext()), "——The End of Book of Lucifel——")
        self.assertIsNotNone(body[1].find("{*}em"))
        self.assertIn("text-align: center", body[1].get("style"))
        self.assertIn("text-indent: 0", body[1].get("style"))
        self.assertEqual(body[2].text, "——全文完——")
        self.assertEqual(body[3].text, "甲——乙")
        self.assertEqual(body[4].text, "The End")
        self.assertIsNotNone(body[5].find("{*}a"))
        second = NormalizationReport(Path("fixture.epub"), True)
        self.assertEqual(normalize_member("chapter.xhtml", result, second, grouped_fanwai_titles=set()), result)
        self.assertEqual(second.total_changes, 0)

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
                Path(d), ["我读过第一卷。"], chapter_title="第一章 初识"
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
