from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from lxml.etree import XMLSyntaxError

from src.inputs.html import parse_xml, read_html_blocks
from src.runtime.files import digest
from src.workflows.prepare import prepare_file


def edition(path: Path, *, epub2=False, fragments=False):
    body = '<h2 id="intro">简介</h2><p>重复。</p><p/><h2 id="one">第1章</h2><p>重复。</p><p>ＭＳＮ，ＱＱ</p>'
    targets = (
        [("简介", "body.xhtml#intro"), ("第1章", "body.xhtml#one")]
        if fragments
        else [("合并正文", "body.xhtml")]
    )
    manifest = '<item id="body" href="body.xhtml" media-type="application/xhtml+xml"/>'
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'
        + "".join(f'<li><a href="{href}">{title}</a></li>' for title, href in targets)
        + "</ol></nav></body></html>"
    )
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
        + "".join(
            f'<navPoint id="n{i}"><navLabel><text>{title}</text></navLabel><content src="{href}"/></navPoint>'
            for i, (title, href) in enumerate(targets)
        )
        + "</navMap></ncx>"
    )
    if epub2:
        manifest += (
            '<item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        )
    else:
        manifest += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:identifier>fixture</dc:identifier><dc:title>测试</dc:title><dc:creator>作者</dc:creator><dc:language>zh-CN</dc:language><dc:date>2008</dc:date></metadata><manifest>'
        + manifest
        + '</manifest><spine><itemref idref="body"/></spine></package>'
    )
    with ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>',
        )
        for name, data in [
            ("book.opf", opf),
            ("nav.xhtml", nav),
            ("toc.ncx", ncx),
            (
                "body.xhtml",
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>正文</title></head><body>'
                + body
                + "</body></html>",
            ),
        ]:
            z.writestr(name, data)


class EpubInputTests(unittest.TestCase):
    def test_multiple_creators_survive_export_import_and_explicit_override(self):
        from src.epub.writer import export_local
        from src.inputs.epub import read_epub_source
        from src.dataset.text import write_prepared_txt
        from tests.fixtures import write_source

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            book = write_source(root, ["Text."], author="Author A")
            book["metadata"]["creators"] = ["Author A", "Author B"]
            export_local(book, root / "book.epub")
            extracted = read_epub_source(root / "book.epub").source
            self.assertEqual(
                extracted["metadata"]["creators"], ["Author A", "Author B"]
            )
            write_prepared_txt(extracted, root / "book.txt")
            self.assertIn("作者：Author A、Author B", (root / "book.txt").read_text())
            overridden, _, _ = prepare_file(
                root / "book.epub", root / "override", author="Author C"
            )
            self.assertEqual(overridden["metadata"]["creator"], "Author C")
            self.assertNotIn("creators", overridden["metadata"])

    def test_epub2_and_epub3_fragment_toc_keep_intro_outside_chapter_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            for epub2 in (False, True):
                root = Path(temporary)
                path = root / f"{epub2}.epub"
                edition(path, epub2=epub2, fragments=True)
                original = path.read_bytes()
                book, _, _ = prepare_file(path, root / str(epub2))
                chapters = list(book["chapters"].values())
                self.assertEqual([c["title"] for c in chapters], ["简介", "第1章"])
                self.assertEqual(chapters[0]["role"], "intro")
                self.assertEqual(chapters[1]["blocks"][0]["runs"][0]["text"], "重复。")
                self.assertEqual(chapters[1]["blocks"][1]["runs"][0]["text"], "MSN，QQ")
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(book["metadata"]["date"], "2008-01-01")
                self.assertFalse(list((root / str(epub2)).glob("*.epub")))

    def test_review_accounts_for_all_blocks_and_preserves_repeats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source.epub"
            edition(path)
            review = {
                "sha256": digest(path.read_bytes()),
                "pages": {
                    "body.xhtml": [
                        {"start": 0, "stop": 3, "role": "intro", "title": "简介"},
                        {"start": 3, "stop": 6, "role": "chapter", "title": "第1章"},
                    ]
                },
            }
            book, _, _ = prepare_file(path, root / "run", review=review)
            chapters = list(book["chapters"].values())
            self.assertEqual(chapters[0]["blocks"][0], chapters[1]["blocks"][0])
            self.assertEqual(
                chapters[0]["blocks"][1], {"kind": "paragraph", "runs": []}
            )
            for invalid in ("stale", "gap", "missing"):
                broken = copy.deepcopy(review)
                if invalid == "stale":
                    broken["sha256"] = "different"
                elif invalid == "gap":
                    broken["pages"]["body.xhtml"][1]["start"] = 4
                else:
                    broken["pages"] = {}
                with self.assertRaises(ValueError):
                    prepare_file(path, root / invalid, review=broken)
                self.assertFalse((root / invalid / "source.json").exists())

    def test_nested_css_entities_and_named_footnotes_keep_reading_order(self):
        data = b'<html><head><style>.note {text-align:right} .em {font-style:italic}</style></head><body><div><p>repeat</p><p>repeat</p><p>text<a href="#note">1</a><span class="em">emphasis</span><br/>next</p><div class="note"><p id="note">note&nbsp;one</p></div></div></body></html>'
        blocks = read_html_blocks(data, "chapter.xhtml", {})
        self.assertEqual(
            ["".join(r["text"] for r in b["runs"]) for b in blocks],
            ["repeat", "repeat", "text1emphasis\nnext", "note\u00a0one"],
        )
        self.assertEqual(blocks[-1]["alignment"], "right")
        self.assertEqual(blocks[2]["runs"][2]["styles"], ["italic"])
        with self.assertRaises(XMLSyntaxError):
            parse_xml(b"<html><p>broken</html>")

    def test_body_images_require_explicit_decision(self):
        data = b'<html><body><p><img src="../i.jpg"/></p></body></html>'
        self.assertEqual(
            read_html_blocks(data, "Text/a.xhtml", {})[0]["asset"], "i.jpg"
        )
        with self.assertRaisesRegex(ValueError, "Mixed inline image"):
            read_html_blocks(data.replace(b"<img", b"text<img"), "Text/a.xhtml", {})
