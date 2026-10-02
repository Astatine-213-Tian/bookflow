from __future__ import annotations

import random
import unittest
from collections import Counter

from experiments.iteration9.pipeline import apply_patches, exact_gold, validate_qa
from experiments.iteration9.study import interleave_volumes, paired_mappings


class PairedStudyTests(unittest.TestCase):
    def test_position_balance_within_reading_stages(self) -> None:
        mappings = paired_mappings(random.Random(17))
        self.assertEqual(Counter(x["候选A"] for x in mappings[:2]), {"old": 1, "new": 1})
        self.assertEqual(Counter(x["候选A"] for x in mappings[2:]), {"old": 3, "new": 3})
        self.assertTrue(all(set(x.values()) == {"old", "new"} for x in mappings))

    def test_early_passages_come_from_distinct_available_volumes(self) -> None:
        source = [({"volume": v, "index": i}, {}) for v in range(1, 5) for i in range(2)]
        result = interleave_volumes(source, random.Random(8))
        self.assertEqual(len({x[0]["volume"] for x in result[:4]}), 4)
        self.assertEqual(len({x[0]["volume"] for x in result[4:]}), 4)
        self.assertEqual(len(source), 8)

    def test_patches_apply_to_original_unicode_offsets_without_cascading(self) -> None:
        source = ["甲走，乙停。"]
        patches = [{"paragraph_index": 0, "before": "甲走", "after": "乙停"},
                   {"paragraph_index": 0, "before": "乙停", "after": "丙跑"}]
        self.assertEqual(apply_patches(source, patches), ["乙停，丙跑。"])
        self.assertEqual(source, ["甲走，乙停。"])

    def test_repeated_and_overlapping_patch_spans_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly once"):
            apply_patches(["好，好。"], [{"paragraph_index": 0, "before": "好", "after": "行"}])
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            apply_patches(["甲走了。"], [{"paragraph_index": 0, "before": "甲走", "after": "他走"},
                                      {"paragraph_index": 0, "before": "走了", "after": "跑了"}])

    def test_qa_requires_literal_source_evidence(self) -> None:
        source = {"english": [{"english": "A person ran."}], "context_before": [], "context_after": []}
        result = {"patches": [{"paragraph_index": 0, "before": "走", "after": "跑", "english_support": "A person walked."}]}
        with self.assertRaisesRegex(ValueError, "literal English"):
            validate_qa(source, ["有人走了。"], result)

    def test_source_crop_is_literal_suffix_and_prefix(self) -> None:
        payload = {"chinese_search_region": [{"line": 2, "text": "目标。前事。目标。"},
                                              {"line": 4, "text": "结尾。后事。"}]}
        result = {"aligned": True, "confidence": "high", "start_line": 2, "end_line": 4,
                  "first_paragraph_quote": "目标。", "last_paragraph_quote": "结尾。"}
        gold = exact_gold(payload, result)
        self.assertEqual(gold["paragraphs"], ["目标。", "结尾。"])
        self.assertEqual(gold["literal_spans"][0]["start"], 6)
        result["first_paragraph_quote"] = "目标！"
        with self.assertRaisesRegex(ValueError, "suffix/prefix"):
            exact_gold(payload, result)

    def test_one_line_crop_requires_unique_identical_boundaries(self) -> None:
        payload = {"chinese_search_region": [{"line": 3, "text": "前。内容。后。"}]}
        result = {"aligned": True, "confidence": "high", "start_line": 3, "end_line": 3,
                  "first_paragraph_quote": "内容。", "last_paragraph_quote": "内容。"}
        self.assertEqual(exact_gold(payload, result)["paragraphs"], ["内容。"])
        result["last_paragraph_quote"] = "后。"
        with self.assertRaises(ValueError):
            exact_gold(payload, result)


if __name__ == "__main__":
    unittest.main()
