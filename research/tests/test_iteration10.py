from __future__ import annotations

import random
import unittest
from collections import Counter

from experiments.iteration6 import prompts as legacy
from experiments.iteration10.pipeline import generation_packets
from experiments.iteration10.study import paired_mappings


class DirectPositiveStudyTests(unittest.TestCase):
    def test_two_treatments_differ_only_by_legacy_positive_condition(self) -> None:
        sample = {"sample_id": "test", "title": "目标书", "english": [{"index": 1, "english": "Someone waited.", "member": "hidden"}],
                  "context_before": ["Before."], "context_after": ["After."], "gold": "不应传入"}
        refs = {"rule": "shared", "examples": [{"title": "目标书", "zh": "禁止同书"}, {"title": "其他书", "zh": "参考"}]}
        bank = [{"title": "另一本书", "english_support": "Someone walked.", "after": "有人走来。", "before": "禁止负例", "reason": "禁止理由"}]
        packets = generation_packets(sample, refs, bank)
        direct_prompt, direct = packets["direct"]
        positive_prompt, positive = packets["positive"]
        self.assertEqual(direct_prompt, legacy.DIRECT)
        self.assertEqual(positive_prompt, legacy.DIRECT + legacy.POSITIVE)
        self.assertEqual({k: v for k, v in positive.items() if k != "wording_examples"}, direct)
        self.assertEqual(positive["wording_examples"], [{"english_context": "Someone walked.", "corrected_chinese_fragment": "有人走来。"}])
        self.assertEqual([x["title"] for x in direct["authentic_examples"]["examples"]], ["其他书"])
        self.assertNotIn("gold", direct)
        self.assertNotIn("member", direct["english"][0])
        self.assertEqual(len(refs["examples"]), 2)

    def test_same_book_wording_example_fails_closed(self) -> None:
        sample = {"title": "书"}
        with self.assertRaises(AssertionError):
            generation_packets(sample, {"examples": []}, [{"title": "书"}])

    def test_method_position_balance_in_each_reading_stage(self) -> None:
        for seed in (0, 37, 2026100110):
            mappings = paired_mappings(random.Random(seed))
            self.assertEqual(Counter(row["候选A"] for row in mappings[:2]), {"direct": 1, "positive": 1})
            self.assertEqual(Counter(row["候选A"] for row in mappings[2:]), {"direct": 3, "positive": 3})
            self.assertTrue(all(set(row.values()) == {"direct", "positive"} for row in mappings))


if __name__ == "__main__":
    unittest.main()
