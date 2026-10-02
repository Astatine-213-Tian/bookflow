from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.iteration9 import reader


class PairedReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        reader.write(self.root / "manifest.json", {"batch": "new"})
        reader.write(self.root / "blind_mapping.json", {"test": {"候选A": "new", "候选B": "old"}})
        reader.write(self.root / "samples/test.json", {"title": "书", "chapter": 3, "volume": 1,
            "reading_stage": "first12", "english": [{"english": "The private target."}]})
        reader.write(self.root / "alignment_inputs/test.json", {"chinese_search_region": [
            {"line": 7, "text": "前事。甲跑来。"}, {"line": 8, "text": "乙笑了。后事。"}]})
        reader.write(self.root / "gold/test.json", {"usable": True, "paragraphs": ["甲跑来。", "乙笑了。"],
            "literal_spans": [{"line": 7, "start": 3, "end": 7}, {"line": 8, "start": 0, "end": 4}]})
        for method in ("old", "new"):
            reader.write(self.root / f"outputs/test/{method}.json", {"paragraphs": ["甲跑来，乙笑了。"]})
        reader.CACHE.clear()

    def tearDown(self) -> None:
        reader.CACHE.clear()
        self.directory.cleanup()

    def case(self) -> dict:
        return reader.get_case(self.root, "test", "paired48", 1, {"候选A": "new", "候选B": "old"})

    def test_blind_payload_omits_english_and_method_and_marks_identical(self) -> None:
        case = self.case()
        self.assertNotIn("english", case)
        self.assertTrue(case["identical_candidates"])
        self.assertTrue(all("method" not in c for c in case["candidates"]))
        self.assertEqual(case["author"], ["甲跑来。", "乙笑了。"])

    def test_wrong_batch_or_stale_display_cannot_receive_vote(self) -> None:
        case = self.case()
        payload = {"display_manifest_sha256": case["display_manifest_sha256"], "choice": "preferred", "candidate_ids": ["A"], "view": {"reading_scope": "first12"}}
        validated = reader.validate_vote(payload, case)
        self.assertEqual(validated["reader_version"], "paired48_v1")
        self.assertTrue(validated["identical_candidates"])
        for update in ({"candidate_ids": ["C"]}, {"display_manifest_sha256": "old-display"}):
            with self.assertRaises(ValueError):
                reader.validate_vote({**payload, **update}, case)

    def test_atomic_save_readback_reselect_clear_and_note_are_new_batch_only(self) -> None:
        with patch.object(reader, "ROOT", self.root), patch.object(reader, "FEEDBACK", self.root / "test_feedback"):
            case = self.case()
            payload = {"sample_key": case["key"], "display_manifest_sha256": case["display_manifest_sha256"], "choice": "preferred", "candidate_ids": ["B"], "note": "测试备注"}
            first = reader.save_vote(payload)
            reader.save_vote({**payload, "choice": "tie", "candidate_ids": ["A", "B"]})
            reader.save_vote({**payload, "choice": "unrated", "candidate_ids": []})
            state = reader.votes()
            self.assertEqual(list(state["votes"]), ["paired48/test"])
            row = state["votes"]["paired48/test"]
            self.assertEqual(row["choice"], "unrated")
            self.assertEqual(row["note"], "测试备注")
            self.assertEqual(row["first_recorded_at"], first["first_recorded_at"])
            self.assertEqual(len((reader.FEEDBACK / "events.jsonl").read_text().splitlines()), 3)

    def test_nonliteral_author_override_is_rejected(self) -> None:
        override = {"sample_id": "test", "gold_sha256": reader.sha(self.root / "gold/test.json"),
                    "alignment_input_sha256": reader.sha(self.root / "alignment_inputs/test.json"),
                    "paragraphs": ["改写。"], "literal_spans": [{"line": 7, "start": 3, "end": 7}]}
        reader.write(self.root / "audit/display_overrides.json", {"records": [override]})
        with self.assertRaisesRegex(ValueError, "Nonliteral"):
            self.case()


if __name__ == "__main__":
    unittest.main()
