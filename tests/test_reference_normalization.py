from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from tests.notion_api import roundtrip

from src.content.blocks import block_text, content_signature
from src.content.references import canonicalize_footnotes
from src.dataset.text import write_prepared_txt
from src.inputs.html import read_html_blocks
from src.inputs.references import resolve_book_references
from tests.test_references import note_blocks


class ReferenceNormalizationTests(unittest.TestCase):
    def test_styled_reference_marker_is_one_occurrence(self):
        html = b"""<html xmlns:epub="http://www.idpf.org/2007/ops"><body>
        <p id="body">Body<a href="#note" epub:type="noteref">[<strong>1</strong>]</a>.</p>
        <aside id="note" epub:type="footnote"><p>Note <strong>body</strong><a href="#body" role="doc-backlink"><em>ba</em>ck</a></p></aside>
        </body></html>"""
        anchors = {}
        original = read_html_blocks(html, "chapter.xhtml", {}, anchors=anchors)
        book = {
            "chapters": {
                "chapter": {"title": "Chapter", "blocks": copy.deepcopy(original)}
            },
            "extras": [],
        }
        resolve_book_references(
            book,
            {
                "anchors": {"chapter.xhtml": anchors},
                "pages": {"chapter.xhtml": original},
            },
        )
        before = copy.deepcopy(book["chapters"]["chapter"])
        chapter = canonicalize_footnotes(before)
        self.assertEqual(before, book["chapters"]["chapter"])
        self.assertEqual(
            [block_text(b) for b in chapter["blocks"]], ["Body[1].", "[1] Note body ↩1"]
        )
        self.assertEqual(
            [r["text"] for r in chapter["blocks"][1]["runs"] if "bold" in r["styles"]],
            ["body"],
        )
        self.assertEqual(canonicalize_footnotes(chapter), chapter)
        self.assertEqual(
            content_signature(roundtrip(chapter["blocks"])),
            content_signature(chapter["blocks"]),
        )

    def test_rebuilds_complete_pairing_and_moves_notes_to_chapter_end(self):
        blocks = note_blocks()
        blocks[1]["runs"][0]["text"] = "[9] 注释 "
        blocks[1]["runs"][-1]["href"] = "#wrong"
        blocks[1]["alignment"] = "right"
        blocks.append(
            {
                "kind": "paragraph",
                "anchor": "second",
                "runs": [
                    {"text": "More", "styles": ["italic"]},
                    {
                        "text": "[7]",
                        "styles": [],
                        "href": "#note",
                        "link_role": "noteref",
                    },
                ],
            }
        )
        original = {"title": "Chapter", "blocks": blocks}
        before = copy.deepcopy(original)
        chapter = canonicalize_footnotes(original)
        self.assertEqual(original, before)
        self.assertEqual(
            [b["anchor"] for b in chapter["blocks"]], ["body", "second", "note"]
        )
        note = chapter["blocks"][-1]
        self.assertEqual(note["alignment"], "right")
        self.assertEqual(block_text(note), "[1] 注释 来源 ↩1.1 ↩1.2")
        self.assertEqual(
            [
                (r["text"], r["href"])
                for r in note["runs"]
                if r.get("link_role") == "backlink"
            ],
            [("↩1.1", "#body"), ("↩1.2", "#second")],
        )
        self.assertEqual(block_text(chapter["blocks"][1]), "More[1]")
        self.assertEqual(canonicalize_footnotes(chapter), chapter)

    def test_adjacent_complete_markers_are_meaningful_repeated_references(self):
        blocks = note_blocks()
        blocks[0]["runs"].append(copy.deepcopy(blocks[0]["runs"][-1]))
        chapter = canonicalize_footnotes({"title": "Chapter", "blocks": blocks})
        self.assertEqual(block_text(chapter["blocks"][0]), "引文[1][1]")
        self.assertEqual(
            [
                r["text"]
                for r in chapter["blocks"][1]["runs"]
                if r.get("link_role") == "backlink"
            ],
            ["↩1.1", "↩1.2"],
        )
        self.assertEqual(canonicalize_footnotes(chapter), chapter)

    def test_multiparagraph_notes_keep_repetition_and_real_backlink_prose(self):
        blocks = note_blocks()
        blocks[1]["runs"] = [{"text": "[8] Repeated.", "styles": ["italic"]}]
        blocks.append(
            {
                "kind": "paragraph",
                "anchor": "continuation",
                "footnote": "note",
                "runs": [
                    {"text": "Repeated. ", "styles": ["italic"]},
                    {
                        "text": "This explains the quotation",
                        "styles": ["bold"],
                        "href": "#body",
                        "link_role": "backlink",
                    },
                ],
            }
        )
        chapter = canonicalize_footnotes({"title": "Chapter", "blocks": blocks})
        self.assertEqual(
            block_text(chapter["blocks"][-1]),
            "[1] Repeated.\n\nRepeated. This explains the quotation ↩1",
        )
        self.assertIn(
            {"text": "This explains the quotation", "styles": ["bold"]},
            chapter["blocks"][-1]["runs"],
        )
        self.assertEqual(canonicalize_footnotes(chapter), chapter)

    def test_unpaired_note_and_missing_return_identity_fail_clearly(self):
        blocks = note_blocks()
        blocks[0]["runs"] = blocks[0]["runs"][:1]
        with self.assertRaisesRegex(ValueError, "no body reference"):
            canonicalize_footnotes({"title": "Chapter", "blocks": blocks})
        blocks = note_blocks()
        blocks[0].pop("anchor")
        with self.assertRaisesRegex(ValueError, "return anchor"):
            canonicalize_footnotes({"title": "Chapter", "blocks": blocks})

    def test_txt_groups_styles_inside_one_link_without_merging_separate_links(self):
        url = "https://example.com/"
        blocks = [
            {
                "kind": "paragraph",
                "runs": [
                    {"text": "read ", "styles": [], "href": url},
                    {"text": "more", "styles": ["bold"], "href": url},
                    {"text": "; ", "styles": []},
                    {"text": "again", "styles": [], "href": url},
                ],
            },
            *note_blocks(),
        ]
        book = {
            "metadata": {"title": "Book", "creator": "Author"},
            "sections": [{"member": "chapter"}],
            "chapters": {"chapter": {"title": "Chapter", "blocks": blocks}},
            "extras": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.txt"
            write_prepared_txt(book, path)
            text = path.read_text()
        self.assertIn(f"read more（{url}）; again（{url}）", text)
        self.assertIn("引文[1]", text)
        self.assertIn("[1] 注释 来源（https://example.com/a?x=1&y=2）", text)
        self.assertNotIn("↩", text)


if __name__ == "__main__":
    unittest.main()
