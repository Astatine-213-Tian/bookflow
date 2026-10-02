from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.iteration8 import reader


class BalancedReaderCropTests(unittest.TestCase):
    def test_last_source_paragraph_can_have_two_sided_boundary_crop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reader.write(root / "samples/test.json", {"title": "书", "volume": 1, "chapter": 1,
                                                      "english": [{"english": "The action."}]})
            gold = root / "gold/test.json"
            reader.write(gold, {"usable": True, "paragraphs": ["首段。", "前事。目标。后事。"]})
            reader.write(root / "manifest.json", {})
            reader.write(root / "outputs/test/direct.json", {"paragraphs": ["译文。"]})
            crop = {"sample_id": "test", "gold_file_sha256": reader.sha(gold),
                    "paragraph_spans": [{"paragraph_index": 0, "start": 0, "end": 3},
                                        {"paragraph_index": 1, "start": 3, "end": 6}],
                    "paragraphs": ["首段。", "目标。"]}
            path = root / "audit/display_crops.json"
            reader.write(path, {"records": [crop]})
            reader.CACHE.clear()
            case = reader.get_case(root, "test", "balanced48", 1, {"候选A": "direct"})
            self.assertEqual(case["author"], ["首段。", "目标。"])
            reader.write(path, {"records": [{**crop, "paragraphs": ["首段。", "改写。"]}]})
            with self.assertRaisesRegex(ValueError, "Nonliteral"):
                reader.get_case(root, "test", "balanced48", 1, {"候选A": "direct"})
            reader.write(path, {"records": [{**crop, "paragraph_spans": crop["paragraph_spans"][1:]}]})
            with self.assertRaisesRegex(ValueError, "omitted or reordered"):
                reader.get_case(root, "test", "balanced48", 1, {"候选A": "direct"})
        reader.CACHE.clear()


if __name__ == "__main__":
    unittest.main()
