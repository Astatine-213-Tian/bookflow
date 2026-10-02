from __future__ import annotations

import copy
import unittest

from experiments.validation.style_feedback.analyze import expand_rating, human_agreement, validate_rating
from experiments.validation.style_feedback.evaluate import DIMENSIONS, feedback_summary


class StyleFeedbackAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {"english_target": ["A person runs."], "english_context_before": ["It was cold."],
                        "english_context_after": [], "author_chinese": ["甲跑来。"],
                        "candidates": [{"candidate_id": "V1", "paragraphs": ["甲跑了过来。"]},
                                       {"candidate_id": "V2", "paragraphs": ["甲奔来。"]}]}
        self.result = {"ranking": [["V1", "V2"]], "assessments": [
            {"candidate_id": c, "scores": {d: 4 if d != "dialogue_rhythm" else 1 for d in DIMENSIONS},
             "not_assessable_dimensions": ["dialogue_rhythm"]} for c in ("V1", "V2")],
            "units": [{"unit_id": "u1", "english_quote": "A person runs.", "author_quote": "甲跑来。",
                       "classification": "comparable_style", "candidates": [
                           {"candidate_id": "V1", "quote": "甲跑了过来。"},
                           {"candidate_id": "V2", "quote": "甲奔来。"}]}]}

    def test_exact_quotes_and_punctuation_mutation(self) -> None:
        self.assertEqual(validate_rating(self.payload, self.result)["exact_comparable_units"], 1)
        self.result["units"][0]["author_quote"] = "甲跑来！"
        checks = validate_rating(self.payload, self.result)
        self.assertEqual(checks["exact_comparable_units"], 0)
        self.assertIn("non-exact author quote", checks["units"][0]["problems"])

    def test_context_only_support_is_flagged_and_excluded_class_not_scored(self) -> None:
        self.result["units"][0]["english_quote"] = "It was cold."
        self.result["units"][0]["classification"] = "edition_content_difference"
        checks = validate_rating(self.payload, self.result)
        self.assertTrue(checks["units"][0]["english_context_only"])
        self.assertEqual(checks["exact_comparable_units"], 0)

    def test_missing_candidate_or_duplicate_ranking_fails(self) -> None:
        self.result["ranking"] = [["V1", "V1"]]
        self.result["units"][0]["candidates"].pop()
        checks = validate_rating(self.payload, self.result)
        self.assertIn("ranking coverage", checks["structural_errors"])
        self.assertIn("candidate coverage", checks["units"][0]["problems"])

    def test_duplicate_text_aliases_get_identical_ranks_and_na_not_averaged(self) -> None:
        expanded = expand_rating(self.result, {"V1": ["direct", "edited"], "V2": ["positive", "contrastive"]})
        self.assertEqual(expanded["direct"], expanded["edited"])
        self.assertEqual(expanded["direct"]["mean"], 4)
        human = {"rows": [{"sample_id": "s", "choice": "preferred", "methods": ["edited"]},
                           {"sample_id": "note", "choice": "unrated", "methods": []}]}
        agreement = human_agreement([{"sample_id": "s", "methods": expanded}], human, set())
        self.assertEqual(agreement["same_single_winner"], [])
        self.assertEqual(agreement["human_choice_in_model_tied_top"], ["s"])

    def test_human_notes_never_become_votes_and_hash_mismatch_fails(self) -> None:
        case = {"sample_id": "s", "title": "乱世为王", "display_manifest_sha256": "display",
                "candidates": [{"id": "A", "output_sha256": "output", "text_sha256": "text"}]}
        vote = {"display_manifest_sha256": "display", "outputs": {"A": {"output_sha256": "output", "text_sha256": "text"}},
                "candidate_ids": [], "choice": "unrated", "note": "AC差不多", "method_revealed": False, "updated_at": "time"}
        summary = feedback_summary({"votes": {"key": vote}}, {"key": case}, {"s": {"候选A": "edited"}})
        self.assertEqual(sum(summary["preference_credits"].values()), 0)
        changed = copy.deepcopy(vote)
        changed["outputs"]["A"]["text_sha256"] = "different"
        with self.assertRaises(AssertionError):
            feedback_summary({"votes": {"key": changed}}, {"key": case}, {"s": {"候选A": "edited"}})


if __name__ == "__main__":
    unittest.main()
