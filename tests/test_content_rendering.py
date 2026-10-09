from __future__ import annotations

import unittest

from lxml import etree as ET
from notion_books import text_blocks, validate_content
from tests.notion_api import roundtrip
from src.content.blocks import content_signature

from src.epub.xhtml import render_blocks
from src.inputs.html import read_html_blocks


class ContentTests(unittest.TestCase):
    def test_h3_size_is_fixed_when_alignment_is_added_or_removed(self):
        for alignment in (None, "left", "center"):
            blocks = [
                {
                    "kind": "heading",
                    "level": 3,
                    "runs": [{"text": "分标题", "styles": []}],
                },
                {
                    "kind": "paragraph",
                    "runs": [{"text": "普通加粗段落", "styles": ["bold"]}],
                },
            ]

            if alignment:
                blocks[0]["alignment"] = alignment
            root = ET.Element("body")
            render_blocks(root, blocks)
            style = root[0].get("style")
            self.assertIn("font-size: 1.1em;", style)
            self.assertNotIn("2em", style)
            self.assertEqual("text-align: center" in style, alignment == "center")
            self.assertEqual(ET.QName(root[0]).localname, "h3")
            self.assertIsNone(root[1].get("style"))

    def test_rich_text_paragraphs_and_literal_punctuation_survive(self):
        xml = """<html xmlns="http://www.w3.org/1999/xhtml"><head/><body>
        <h2>第1章 开始</h2><p>“测试，<strong>保留粗体</strong>……”</p>
        <p>* * * 是正文</p><p>1. 不是列表</p><p>换行<br/>下一行</p>
        <p></p><h3>（一）</h3><p><em>斜体</em>与普通文字</p>
        </body></html>""".encode()
        before = read_html_blocks(xml, "chapter.xhtml", {})[1:]
        after = roundtrip(before)
        self.assertEqual(text_blocks(before), text_blocks(after))
        self.assertEqual(after[0]["runs"][1]["styles"], ["bold"])
        self.assertEqual(after[-1]["runs"][0]["styles"], ["italic"])

    def test_unknown_source_blocks_stop_instead_of_dropping_text(self):
        with self.assertRaises(ValueError):
            read_html_blocks(
                b'<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>Title</h2><video>Unsupported content</video></body></html>',
                "chapter.xhtml",
                {},
            )
        with self.assertRaises(ValueError):
            validate_content([{"kind": "image", "runs": []}])

    def test_literal_rule_text_is_escaped_instead_of_becoming_a_notion_divider(self):
        blocks = [
            {
                "kind": "paragraph",
                "runs": [{"text": "-----", "styles": []}],
                "alignment": "center",
            }
        ]
        self.assertEqual(
            content_signature(roundtrip(blocks)), content_signature(blocks)
        )

    def test_center_is_a_paragraph_property_not_a_text_pattern(self):
        xml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>标题</h2>
        <p style="text-align: center; text-indent: 0;">任意一段普通文字</p>
        <p>——本卷完——</p>
        <p style="text-align: center; text-indent: 0;"><strong>（一）</strong></p>
        </body></html>""".encode()
        original = read_html_blocks(xml, "chapter.xhtml", {})[1:]
        blocks = roundtrip(original)
        self.assertEqual(content_signature(blocks), content_signature(original))
        self.assertEqual(blocks[0]["alignment"], "center")
        self.assertNotIn("alignment", blocks[1])
        self.assertEqual(blocks[2]["kind"], "paragraph")
        root = ET.Element("body")
        render_blocks(root, blocks)
        self.assertEqual(root[0].get("style"), "text-align: center; text-indent: 0;")
        self.assertIsNone(root[1].get("style"))
        self.assertEqual(ET.QName(root[2]).localname, "p")
        self.assertEqual(ET.QName(root[2][0]).localname, "strong")

    def test_author_notes_keep_body_size_and_list_structure(self):
        blocks = [{"kind": "paragraph", "runs": [{"text": "Narrative", "styles": []}]},
                  {"kind": "divider", "runs": []},
                  {"kind": "paragraph", "runs": [{"text": "作者有话说：", "styles": ["bold"]}]},
                  {"kind": "paragraph", "runs": [{"text": "超阶法宝：", "styles": []}]},
                  {"kind": "bulleted_list_item", "runs": [{"text": "东皇钟", "styles": []}],
                   "children": [{"kind": "numbered_list_item", "runs": [{"text": "说明", "styles": []}]}]}]
        after = roundtrip(blocks)
        self.assertEqual(content_signature(after), content_signature(blocks))
        root = ET.Element("body")
        render_blocks(root, after)
        section = root.find("{*}section")
        self.assertIsNotNone(section)
        self.assertEqual(root[0].text, "Narrative")
        self.assertEqual(section.get("class"), "author-note")
        self.assertEqual(ET.QName(section[0]).localname, "p")
        self.assertIsNotNone(section[0].find("{*}strong"))
        self.assertIsNotNone(section.find("{*}ul/{*}li/{*}ol/{*}li"))
        self.assertFalse(section.xpath(".//*[local-name()='h2' or local-name()='h3']"))
        # The section wrapper remains transparent to EPUB source import.
        html = ET.Element("html")
        html.append(root)
        imported = read_html_blocks(ET.tostring(html), "notes.xhtml", {})
        self.assertIn("作者有话说：", ["".join(r["text"] for r in b["runs"]) for b in imported])
