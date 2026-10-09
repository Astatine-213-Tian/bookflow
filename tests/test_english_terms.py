from __future__ import annotations

import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from src.content.blocks import block_text
from src.content.english_terms import CANONICAL_TERMS, normalize_english_terms
from src.content.normalization import NormalizationReport
from src.content.normalize import normalize_chapter, normalize_text
from src.epub.cleanup import normalize_member


class EnglishTermTests(unittest.TestCase):
    def test_all_iphone_casing_combinations_and_no_spelling_guess(self):
        for letters in itertools.product(*[(c.lower(), c.upper()) for c in "iphone"]):
            self.assertEqual(normalize_text("".join(letters)), "iPhone")
        self.assertEqual(normalize_text("IPONE"), "IPONE")

    def test_reviewed_terms_canonicalize_once_without_changing_spelling(self):
        for canonical in CANONICAL_TERMS.values():
            for before in (canonical.lower(), canonical.upper(), canonical.swapcase()):
                with self.subTest(before=before):
                    after, count = normalize_english_terms(before)
                    self.assertEqual(after, canonical)
                    self.assertEqual(after.casefold(), before.casefold())
                    self.assertEqual(count, int(before != canonical))
                    self.assertEqual(normalize_english_terms(after), (after, 0))

    def test_chinese_boundaries_models_and_ambiguous_words(self):
        self.assertEqual(
            normalize_text("10月用IPHONE15、IPAD和github。"),
            "10 月用 iPhone15、iPad 和 GitHub。",
        )
        self.assertEqual(normalize_text("MAC地址与MAC电脑"), "MAC 地址与 Mac 电脑")
        value = "myiphone iphones iphone_case iphone12pro github123 apple python app it id us word"
        self.assertEqual(normalize_english_terms(value), (value, 0))

    def test_addresses_paths_handles_and_code_are_preserved(self):
        for value in (
            "https://example.com/IPHONE",
            "IPHONE@example.com",
            "github.com/IPAD",
            "IPHONE.txt",
            "/tmp/IPHONE",
            "C:\\IPHONE\\IPAD",
            "@iphone",
            "#IPHONE",
            "`IPHONE`",
            "```\nIPHONE\n```",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_english_terms(value), (value, 0))
        self.assertEqual(
            normalize_english_terms("xiphone", protected_ranges=[(0, 1)]),
            ("xiphone", 0),
        )

    def test_semantic_runs_keep_link_targets_styles_and_code_case(self):
        chapter = {
            "title": "章",
            "blocks": [
                {
                    "kind": "paragraph",
                    "runs": [
                        {
                            "text": "IPH",
                            "styles": ["bold"],
                            "href": "https://example.com/IPHONE",
                        },
                        {"text": "ONE", "styles": ["italic"]},
                        {"text": " 与 ", "styles": []},
                        {"text": "IPHONE", "styles": ["code"]},
                    ],
                }
            ],
        }
        result = normalize_chapter(chapter)
        runs = result["blocks"][0]["runs"]
        self.assertEqual(block_text(result["blocks"][0]), "iPhone 与 IPHONE")
        self.assertEqual(runs[0]["href"], chapter["blocks"][0]["runs"][0]["href"])
        self.assertEqual(runs[0]["styles"], ["bold"])
        self.assertEqual(runs[-1], chapter["blocks"][0]["runs"][-1])
        self.assertEqual(normalize_chapter(result), result)

    def test_archive_markup_and_code_have_the_same_casing_rules(self):
        raw = b'<html><body><p><a href="https://example.com/IPHONE">IP<b>HONE</b></a> <code>IPHONE</code> x<i>iphone</i></p></body></html>'
        report = NormalizationReport(Path("fixture.epub"), True)
        result = normalize_member(
            "chapter.xhtml", raw, report=report, grouped_fanwai_titles=set()
        )
        p = ET.fromstring(result).find("body/p")
        self.assertEqual("".join(p.itertext()), "iPhone IPHONE xiphone")
        self.assertEqual(p.find("a").get("href"), "https://example.com/IPHONE")
        self.assertEqual(p.find("a/b").text, "hone")
        self.assertEqual(p.findtext("code"), "IPHONE")
        self.assertEqual(
            normalize_member(
                "chapter.xhtml",
                result,
                report=NormalizationReport(Path("fixture.epub"), True),
                grouped_fanwai_titles=set(),
            ),
            result,
        )


if __name__ == "__main__":
    unittest.main()
