from __future__ import annotations

import unittest

from src.translation.output import translated_chapter_blocks
from src.translation.pipeline import prepare_translation_run
from src.translation.positive_scene import alignment_errors, prompt_glossary, resolve_issues, scene_windows
from src.translation.style_transfer_assets import sha256_json


class PositiveSceneTests(unittest.TestCase):
    def test_aliases_survive_prompt_serialization(self) -> None:
        import json
        glossary = {"terms": {"Fire-Bearing Warrior": {"zh": "持火人", "aliases": ["Flameguard Paladin"]}}}
        payload = json.loads(json.dumps(prompt_glossary(glossary, "The Flameguard Paladin left.")))
        self.assertEqual(payload["Flameguard Paladin"], "持火人")
        self.assertEqual(payload["Fire-Bearing Warrior"], "持火人")
        self.assertNotIn("Flameguard Paladin", prompt_glossary(glossary, "A warrior came."))

    def test_alignment_requires_both_streams_in_order_exactly_once(self) -> None:
        request = {"english": [{"index": 8}, {"index": 9}, {"index": 10}], "chinese": ["甲乙", "丙"]}
        valid = {"groups": [{"english_indices": [8, 9], "chinese_indices": [0]},
                            {"english_indices": [10], "chinese_indices": [1]}]}
        self.assertEqual(alignment_errors(request, valid), [])
        for english, chinese in (([8, 9, 9], [0, 1]), ([8, 10, 9], [0, 1]),
                                 ([8, 9, 10], [1, 0]), ([8, 9, 10], [0])):
            self.assertTrue(alignment_errors(request, {"groups": [
                {"english_indices": english, "chinese_indices": chinese}]}))

    def test_grouped_rendering_preserves_chinese_and_source_inline_markup(self) -> None:
        chapter = {"paragraphs": [{"index": 0}, {"index": 1}], "blocks": [
            {"type": "content", "index": 0, "html": "<p>He <i>ran</i>.</p>"},
            {"type": "content", "index": 1, "html": "<p>He arrived.</p>"}]}
        data = {"groups": [{"english_indices": [0, 1], "paragraphs": ["他跑来了。", "“到了。”"]}]}
        parts = translated_chapter_blocks(chapter, data)
        self.assertEqual(parts[:2], [x["html"] for x in chapter["blocks"]])
        self.assertEqual(parts[2:], ['<p class="zh-translation" xml:lang="zh-CN">他跑来了。</p>',
                                    '<p class="zh-translation" xml:lang="zh-CN">“到了。”</p>'])
        chapter["blocks"].insert(1, {"type": "separator", "html": "<hr/>"})
        with self.assertRaisesRegex(ValueError, "separator"):
            translated_chapter_blocks(chapter, data)

    def test_scene_windows_keep_short_tails_and_source_separators(self) -> None:
        rows = [{"index": i, "english": "word " * count} for i, count in enumerate((130, 130, 30, 40))]
        blocks = [{"type": "content", "index": i} for i in range(4)]
        blocks.insert(3, {"type": "separator", "html": "<hr/>"})
        windows = scene_windows({"paragraphs": rows, "blocks": blocks}, 230)
        self.assertEqual([[x["index"] for x in w] for w in windows], [[0, 1, 2], [3]])

    def test_only_adjudicated_exact_unique_repairs_are_applied(self) -> None:
        draft = {"paragraphs": ["他有两把剑。", "他笑了。"]}
        qa = {"issues": [{"paragraph": 0, "before": "两把", "after": "三把"},
                         {"paragraph": 1, "before": "笑了", "after": "露出了一个笑容"}]}
        resolution = {"qa_sha256": sha256_json(qa), "decisions": [
            {"issue": 0, "apply": True, "reason": "English says three swords"},
            {"issue": 1, "apply": False, "reason": "Both mean smiled; no factual correction"}]}
        self.assertEqual(resolve_issues(draft, qa, resolution), ["他有三把剑。", "他笑了。"])
        self.assertEqual(draft["paragraphs"], ["他有两把剑。", "他笑了。"])
        with self.assertRaisesRegex(ValueError, "stale"):
            resolve_issues(draft, qa, {**resolution, "qa_sha256": "outdated"})
        with self.assertRaisesRegex(ValueError, "exact and unique"):
            resolve_issues({"paragraphs": ["两把，两把。", "他笑了。"]}, qa, resolution)

    def test_selected_method_cannot_silently_fall_back_to_neutral(self) -> None:
        from pathlib import Path
        with self.assertRaisesRegex(ValueError, "scene-positive"):
            prepare_translation_run(snapshot_dir=Path("missing"),
                config={"translation": {"method": "direct_scene_positive"}})


if __name__ == "__main__":
    unittest.main()
