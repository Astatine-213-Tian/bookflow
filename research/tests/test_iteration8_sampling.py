from __future__ import annotations

import random
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from experiments.iteration8 import study


class BalancedSamplingTests(unittest.TestCase):
    def test_fractional_main_story_stays_in_one_sampling_unit(self) -> None:
        common = {"volume": 1, "en_epub_path": "book.epub"}
        chapters = [{**common, "en_chapter": "14", "en_members": ["a.xhtml"],
                     "clean_start_line": 100, "clean_end_line": 200},
                    {**common, "en_chapter": "14.5", "en_members": ["b.xhtml"],
                     "clean_start_line": 150, "clean_end_line": 250},
                    {**common, "en_chapter": "15", "en_members": ["c.xhtml"],
                     "clean_start_line": 220, "clean_end_line": 300}]
        grouped = study.chapter_groups(chapters)
        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0]["en_members"], ["a.xhtml", "b.xhtml"])
        self.assertEqual(grouped[0]["clean_end_line"], 250)
        self.assertEqual(chapters[0]["en_members"], ["a.xhtml"])

    def test_candidate_positions_and_adjacent_order_are_balanced(self) -> None:
        mapping = study.balanced_mappings(random.Random(2026092608))
        self.assertEqual(len(mapping), 8)
        for position in "ABCD":
            self.assertEqual(Counter(row[f"候选{position}"] for row in mapping),
                             Counter({method: 2 for method in study.METHODS}))
        pairs = Counter(pair for row in mapping for pair in zip(list(row.values()), list(row.values())[1:]))
        self.assertEqual(len(pairs), 12)
        self.assertEqual(set(pairs.values()), {2})

    def test_previous_targets_and_references_exclude_neighboring_context(self) -> None:
        rows = [{"index": i, "member": "part.xhtml", "p_index": i+10} for i in range(20)]
        prior = [{"source_epub": "book.epub", "english": rows[5:7]}]
        refs = [{"sources": {"en_epub": "book.epub", "en_xhtml_member": "part.xhtml",
                             "en_p_indexes_zero_based_all_p": [24, 25]}}]
        ranges = study.blocked_regions({"en_epub_path": "book.epub"}, rows, prior, refs)
        self.assertEqual(ranges, [(3, 8), (12, 17)])
        self.assertTrue(study.overlaps((8, 11), ranges[0]))
        self.assertFalse(study.overlaps((9, 11), ranges[0]))

    def test_only_numeric_note_links_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("a.xhtml", '<html><body><p>He paid 12 coins.<span><a href="notes#endnote1">1</a></span>'
                                 ' Keep <a href="chapter2">2</a> and <a href="notes#endnote2">the explanation</a>.</p></body></html>')
            rows, changes = study.source_rows({"en_epub_path": str(path), "en_members": ["a.xhtml"]})
        self.assertEqual(rows[0]["english"], "He paid 12 coins. Keep 2 and the explanation.")
        self.assertEqual(len(changes), 1)


if __name__ == "__main__":
    unittest.main()
