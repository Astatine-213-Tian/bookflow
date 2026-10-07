from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
from notion_books import from_markdown, to_markdown

from src.content.blocks import content_signature
from src.content.contract import validate_book
from src.content.normalize import normalize_chapter
from src.content.references import canonicalize_footnotes
from src.dataset.text import write_prepared_txt
from src.epub.writer import export_local
from src.inputs.epub import read_epub_source
from tests.fixtures import write_source


def note_blocks():
    return [
        {
            "kind": "quote",
            "anchor": "body",
            "runs": [
                {"text": "引文", "styles": []},
                {"text": "[1]", "styles": [], "href": "#note", "link_role": "noteref"},
            ],
        },
        {
            "kind": "paragraph",
            "anchor": "note",
            "footnote": "note",
            "runs": [
                {"text": "[1] 注释 ", "styles": []},
                {
                    "text": "来源",
                    "styles": ["bold"],
                    "href": "https://example.com/a?x=1&y=2",
                },
                {"text": " ", "styles": []},
                {"text": "↩1", "styles": [], "href": "#body", "link_role": "backlink"},
            ],
        },
    ]


class ReferenceTests(unittest.TestCase):
    def test_epub_keeps_line_breaks_and_whitespace_inside_styled_links(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            book = write_source(root, ["fixture"])
            chapter = next(iter(book["chapters"].values()))
            chapter["blocks"] = [
                {
                    "kind": "paragraph",
                    "alignment": "center",
                    "runs": [
                        {
                            "text": "\n  链接文字\n",
                            "styles": ["underline"],
                            "href": "https://example.com/",
                        },
                        {"text": "  ", "styles": [], "href": "https://example.com/"},
                    ],
                }
            ]
            path = root / "book.epub"
            export_local(book, path)
            recovered = next(iter(read_epub_source(path).source["chapters"].values()))
            self.assertEqual(
                content_signature(chapter["blocks"]),
                content_signature(recovered["blocks"]),
            )

    def test_notion_round_trip_recovers_footnotes_without_checkpoint(self):
        blocks = note_blocks()
        markdown = to_markdown(blocks)
        self.assertEqual(
            content_signature(from_markdown(markdown)), content_signature(blocks)
        )
        remote = markdown.replace(
            "#note", "https://www.notion.so/" + "a" * 32 + "#" + "b" * 32
        ).replace("#body", "https://www.notion.so/" + "a" * 32 + "#" + "c" * 32)
        recovered = from_markdown(remote)
        self.assertEqual(recovered[0]["kind"], "quote")
        self.assertEqual(recovered[0]["runs"][1]["href"], "#" + recovered[1]["anchor"])
        self.assertEqual(recovered[1]["runs"][-1]["href"], "#" + recovered[0]["anchor"])
        self.assertEqual(recovered[1]["footnote"], recovered[1]["anchor"])

    def test_normalization_preserves_targets_and_reference_identity(self):
        blocks = note_blocks()
        blocks[0]["runs"][0].update(
            text="ＭＳＮ　ＤＯＧＳ！", href="https://example.com/ＭＳＮ?x=ＱＱ"
        )
        ch = normalize_chapter({"title": "正文", "blocks": blocks})
        self.assertEqual(ch["blocks"][0]["runs"][0]["text"], "MSN DOGS！")
        self.assertEqual(
            ch["blocks"][0]["runs"][0]["href"], blocks[0]["runs"][0]["href"]
        )
        self.assertEqual(ch["blocks"][0]["runs"][1]["link_role"], "noteref")
        self.assertEqual(canonicalize_footnotes(ch), ch)

    def test_book_notion_epub_round_trip_and_txt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            book = write_source(root, ["fixture"])
            ch = next(iter(book["chapters"].values()))
            ch["blocks"] = from_markdown(to_markdown(note_blocks()))
            out = root / "book.epub"
            export_local(book, out)
            parsed = read_epub_source(out).source
            actual = next(iter(parsed["chapters"].values()))["blocks"]
            self.assertEqual(content_signature(actual), content_signature(ch["blocks"]))
            with ZipFile(out) as archive:
                raw = archive.read("EPUB/chapter_0001.xhtml")
                xml = ET.fromstring(raw)
                self.assertEqual(
                    len(
                        xml.xpath(
                            '//*[@epub:type="noteref"]',
                            namespaces={"epub": "http://www.idpf.org/2007/ops"},
                        )
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        xml.xpath(
                            '//*[@epub:type="footnote"]',
                            namespaces={"epub": "http://www.idpf.org/2007/ops"},
                        )
                    ),
                    1,
                )
                self.assertEqual(len(xml.xpath('//*[local-name()="blockquote"]')), 1)
                for a in xml.xpath('//*[local-name()="a"]'):
                    href = a.get("href")
                    frag = href.split("#")[-1]
                    if "#" in href:
                        self.assertEqual(len(xml.xpath("//*[@id=$id]", id=frag)), 1)
            write_prepared_txt(parsed, root / "book.txt")
            text = (root / "book.txt").read_text()
            self.assertIn("来源（https://example.com/a?x=1&y=2）", text)
            self.assertIn("[1] 注释", text)
            self.assertNotIn("↩", text)

    def test_broken_and_unsafe_references_fail_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            book = write_source(Path(d), ["text"])
            ch = next(iter(book["chapters"].values()))
            ch["blocks"] = note_blocks()
            validate_book(book)
            for href in [
                "#missing",
                "javascript:alert(1)",
                "file:///secret",
                "relative.xhtml#note",
            ]:
                broken = copy.deepcopy(book)
                next(iter(broken["chapters"].values()))["blocks"][0]["runs"][1][
                    "href"
                ] = href
                with self.assertRaises(ValueError):
                    validate_book(broken)
        with self.assertRaises(Exception):
            from_markdown("[evil](javascript:alert)")

    def test_native_target_verification_catches_swapped_footnote_urls(self):
        from src.notion.references import verify_bound_content, bind_references

        blocks = note_blocks()
        bindings = {
            "body": "https://www.notion.so/" + "a" * 32 + "#" + "b" * 32,
            "note": "https://www.notion.so/" + "a" * 32 + "#" + "c" * 32,
        }
        markdown = to_markdown(bind_references(blocks, bindings))
        self.assertTrue(verify_bound_content(markdown, blocks, bindings))
        wrong = markdown.replace("#" + "c" * 32, "#" + "d" * 32)
        self.assertFalse(verify_bound_content(wrong, blocks, bindings))

    def test_epub2_notes_and_multi_paragraph_epub3_notes_keep_prose(self):
        from src.inputs.html import read_html_blocks
        from src.inputs.references import resolve_book_references

        html = b"""<html xmlns:epub="http://www.idpf.org/2007/ops"><body><p id="r">body<a epub:type="noteref" href="#n">1</a></p><aside id="n" epub:type="footnote"><p>2011 was a year.</p><p>Second paragraph.<a role="doc-backlink" href="#r">back</a></p></aside></body></html>"""
        anchors = {}
        blocks = read_html_blocks(html, "one.xhtml", {}, anchors=anchors)
        book = {
            "chapters": {"one": {"title": "one", "blocks": copy.deepcopy(blocks)}},
            "extras": [],
        }
        resolve_book_references(
            book, {"anchors": {"one.xhtml": anchors}, "pages": {"one.xhtml": blocks}}
        )
        chapter = canonicalize_footnotes(book["chapters"]["one"])
        self.assertEqual(len(chapter["blocks"]), 2)
        note = "".join(r["text"] for r in chapter["blocks"][1]["runs"])
        self.assertEqual(note, "[1] 2011 was a year.\n\nSecond paragraph. ↩1")
        self.assertEqual(
            content_signature(from_markdown(to_markdown(chapter["blocks"]))),
            content_signature(chapter["blocks"]),
        )
