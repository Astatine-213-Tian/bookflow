from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.content.author_notes import missing_note_dividers, plain_note
from src.content.blocks import block_text
from src.content.contract import metadata_defaults
from src.content.prepared import load_prepared_source, save_source
from src.content.proofread import apply_plan, plan_proofread
from src.crawler.providers.jjwxc.reference import (
    access_status,
    parse_body,
    reference_url,
)
from src.notion.proofread import (
    acknowledge_append,
    append_payload,
    apply_edits,
    native_equal,
    text_payload,
)

LEFT = "天色渐渐明亮起来，众人沿着山间小路继续向前走去。"
RIGHT = "第二天早上他推开房门，看见院子里的梅花已经开了。"


def paragraph(text: str) -> dict:
    return {"kind": "paragraph", "runs": [{"text": text, "styles": []}] if text else []}


def book(*texts: str) -> dict:
    return {
        "chapters": {
            "one": {"title": "第一章", "blocks": [paragraph(t) for t in texts]}
        },
        "sections": [{"member": "one"}],
        "extras": [],
    }


class ReferenceParserTests(unittest.TestCase):
    def test_only_real_br_gaps_and_no_comment_counts(self):
        html = """<br><span class="onebook_paragraph_comment_anchor"><span class="onebook_paragraph_comment_text">甲</span><span class="onebook_paragraph_comment_bubble">99</span></span>
        <br><br><br><span class="onebook_paragraph_comment_anchor"><span class="onebook_paragraph_comment_text">乙@无限好文，尽在晋江文学城</span></span><br>"""
        self.assertEqual(
            [block_text(b) for b in parse_body(html)], ["甲", "", "", "乙"]
        )

    def test_access_outcomes_are_not_subscription_claims(self):
        for path, expected in [
            ("login.php", "login_required"),
            ("backend/buynovel.php", "purchase_page"),
        ]:
            self.assertEqual(
                access_status(
                    {"url": "https://my.jjwxc.net/" + path},
                    novel_id="1",
                    chapter_id="2",
                ),
                expected,
            )
        self.assertEqual(
            access_status(
                {"url": "https://www.jjwxc.net/onebook.php?novelid=1&chapterid=3"},
                novel_id="1",
                chapter_id="2",
            ),
            "wrong_chapter",
        )
        with self.assertRaises(ValueError):
            reference_url("https://example.com/?novelid=1")


class ProofreadTests(unittest.TestCase):
    def test_existing_notes_normalize_but_prose_and_appended_edition_do_not(self):
        original = book(
            "正文10月用IPHONE",
            "作者有话说：10月用IPHONE",
            "推荐github。",
            "——卷三·终——",
            "【第一版】",
            "另一版10月用IPHONE",
        )
        original["chapters"]["one"]["blocks"][2]["runs"][0].update(
            styles=["bold"], href="https://github.com/IPHONE"
        )
        reference = book("完全不同的参考版本")
        candidate, ops = apply_plan(
            original, reference, plan_proofread(original, reference)
        )
        rows = candidate["chapters"]["one"]["blocks"]
        self.assertEqual(
            [block_text(b) for b in rows],
            [
                "正文10月用IPHONE",
                "",
                "作者有话说：10 月用 iPhone",
                "推荐 GitHub。",
                "——卷三·终——",
                "【第一版】",
                "另一版10月用IPHONE",
            ],
        )
        self.assertEqual(rows[3]["runs"][0]["styles"], ["bold"])
        self.assertEqual(rows[3]["runs"][0]["href"], "https://github.com/IPHONE")
        self.assertEqual(
            sum(o.get("reason") == "author_note_normalization" for o in ops), 2
        )
        self.assertFalse(plan_proofread(candidate, reference)["operations"])

    def test_gap_recovery_preserves_edition_additions_styles_and_is_idempotent(self):
        original = book("出版版独有的开头", LEFT, RIGHT, "出版版独有的结尾")
        original["chapters"]["one"]["blocks"][1]["runs"][0]["styles"] = ["bold"]
        reference = book(LEFT, "", "", RIGHT)
        plan = plan_proofread(original, reference)
        result, ops = apply_plan(original, reference, plan)
        self.assertEqual(len(ops), 1)
        self.assertEqual(
            [block_text(b) for b in result["chapters"]["one"]["blocks"]],
            ["出版版独有的开头", LEFT, "", "", RIGHT, "出版版独有的结尾"],
        )
        self.assertEqual(
            result["chapters"]["one"]["blocks"][1],
            original["chapters"]["one"]["blocks"][1],
        )
        self.assertFalse(plan_proofread(result, reference)["operations"])

    def test_repeated_context_and_large_differences_do_not_force_edits(self):
        reference = book(LEFT, "", RIGHT)
        for original in (
            book(LEFT, RIGHT, LEFT, RIGHT),
            book("另一版本完全不同的文字"),
            book(LEFT, "出版版新增的场景", RIGHT),
        ):
            self.assertFalse(plan_proofread(original, reference)["operations"])

    def test_moved_extra_is_located_by_content(self):
        original = book("这是主文")
        original["extras"] = [
            {"title": "已移走的番外", "blocks": [paragraph(LEFT), paragraph(RIGHT)]}
        ]
        plan = plan_proofread(original, book(LEFT, "", RIGHT))
        self.assertEqual(plan["operations"][0]["member"], "extra:0")

    def test_font_obfuscation_supports_layout_but_not_text_replacement(self):
        reference = book(LEFT.replace("天", "\ue123"), "", RIGHT)
        plan = plan_proofread(book(LEFT, RIGHT), reference)
        self.assertEqual(plan["operations"][0]["count"], 1)
        result, _ = apply_plan(book(LEFT, RIGHT), reference, plan)
        self.assertEqual(block_text(result["chapters"]["one"]["blocks"][0]), LEFT)

    def test_structural_divider_and_existing_extra_blanks_are_preserved(self):
        original = book(LEFT, "", "", RIGHT)
        self.assertFalse(plan_proofread(original, book(LEFT, "", RIGHT))["operations"])
        original["chapters"]["one"]["blocks"][1] = {"kind": "divider", "runs": []}
        self.assertFalse(
            plan_proofread(original, book(LEFT, "", "", "", RIGHT))["operations"]
        )

    def test_spacing_requires_matching_reference_and_keeps_intentional_separation(self):
        original = book(LEFT.replace("山间", "山 间"))
        plan = plan_proofread(original, book(LEFT))
        result, _ = apply_plan(original, book(LEFT), plan)
        self.assertEqual(block_text(result["chapters"]["one"]["blocks"][0]), LEFT)
        self.assertFalse(plan_proofread(original, original)["operations"])

    def test_only_suspects_are_reviewed_and_repair_is_minimal_evidence_bound(self):
        broken = LEFT.replace("山间", "山�")
        original, reference = book(broken), book(LEFT)
        plan = plan_proofread(original, reference)
        self.assertEqual(len(plan["findings"]), 1)
        finding = plan["findings"][0]
        row = {
            "id": finding["id"],
            "verdict": "repair",
            "confidence": "high",
            "reason": "replacement glyph in otherwise identical context",
            "old": "�",
            "new": "间",
        }
        decisions = {"fingerprint": plan["fingerprint"], "reviews": [row]}
        result, _ = apply_plan(original, reference, plan, decisions)
        self.assertEqual(block_text(result["chapters"]["one"]["blocks"][0]), LEFT)
        row["new"] = "虚构"
        with self.assertRaises(ValueError):
            apply_plan(original, reference, plan, decisions)
        # A different valid name/edition is not itself a suspect signal.
        self.assertFalse(
            plan_proofread(book(LEFT.replace("山间", "林间")), reference)["findings"]
        )

    def test_stale_content_and_decisions_are_rejected(self):
        original, reference = book(LEFT, RIGHT), book(LEFT, "", RIGHT)
        plan = plan_proofread(original, reference)
        with self.assertRaises(ValueError):
            apply_plan(book(LEFT, RIGHT, "new"), reference, plan)
        with self.assertRaises(ValueError):
            apply_plan(
                original, reference, plan, {"fingerprint": "stale", "reviews": []}
            )

    def test_author_notes_are_plain_text_and_image_captions_require_review(self):
        parsed = plain_note(
            '<p>历史说明</p><a href="https://example.org">推荐书名</a><br><img src="broken"><br>下面这张是作者的画<br>读者投了1个地雷'
        )
        self.assertEqual(
            parsed["lines"], ["历史说明", "推荐书名", "下面这张是作者的画"]
        )
        self.assertEqual(parsed["image_reference_lines"], [2])
        self.assertFalse(
            plain_note('<img src="broken"><a href="https://example.org">点我</a>')[
                "lines"
            ]
        )

    def test_missing_note_added_after_short_ending_and_not_duplicated(self):
        original, reference = book(LEFT, RIGHT, "全文完"), book(LEFT, RIGHT, "全文完")
        reference["chapters"]["one"]["source"] = {"id": "1"}
        evidence = {
            "chapters": {"1": {"note_present": True, "note_html": "明天继续更新"}}
        }
        plan = plan_proofread(original, reference, reference_evidence=evidence)
        result, ops = apply_plan(original, reference, plan)
        self.assertEqual([op["kind"] for op in ops], ["append_note"])
        self.assertEqual(
            [block_text(b) for b in result["chapters"]["one"]["blocks"][-2:]],
            ["作者有话说：", "明天继续更新"],
        )
        self.assertFalse(
            plan_proofread(result, reference, reference_evidence=evidence)["operations"]
        )

    def test_partial_note_can_only_insert_missing_source_lines_at_reviewed_anchors(
        self,
    ):
        original = book(
            LEFT,
            RIGHT,
            "作者有话要说：",
            "已有的解释",
            "——他始终认定信念",
            "【另一版正文】",
            "另一版正文保留",
        )
        reference = book(LEFT, RIGHT)
        reference["chapters"]["one"]["source"] = {"id": "1"}
        evidence = {
            "chapters": {
                "1": {"note_present": True, "note_html": "缺失的开头<br>已有的解释"}
            }
        }
        plan = plan_proofread(original, reference, reference_evidence=evidence)
        note = plan["notes"][0]
        row = {
            "id": note["id"],
            "verdict": "approved",
            "insertions": [{"after_index": 2, "line_indices": [0]}],
            "reason": "Only the opening sentence is missing",
        }
        decisions = {"fingerprint": plan["fingerprint"], "reviews": [row]}
        result, ops = apply_plan(
            original, reference, plan, completion_decisions=decisions
        )
        self.assertEqual([op["kind"] for op in ops], ["insert_divider", "insert_note"])
        self.assertEqual(
            [block_text(b) for b in result["chapters"]["one"]["blocks"]],
            [
                LEFT,
                RIGHT,
                "",
                "作者有话要说：",
                "缺失的开头",
                "已有的解释",
                "——他始终认定信念",
                "【另一版正文】",
                "另一版正文保留",
            ],
        )
        self.assertEqual([r["index"] for r in note["existing_context"]], [2, 3, 4])
        self.assertEqual(result["chapters"]["one"]["blocks"][2]["kind"], "divider")
        self.assertEqual(
            plan_proofread(result, reference, reference_evidence=evidence)["notes"][0][
                "status"
            ],
            "already_present",
        )
        row["insertions"][0]["after_index"] = 0
        with self.assertRaises(ValueError):
            apply_plan(original, reference, plan, completion_decisions=decisions)
        row["insertions"][0] = {"after_index": 2, "line_indices": [1]}
        with self.assertRaises(ValueError):
            apply_plan(original, reference, plan, completion_decisions=decisions)

    def test_invalid_flagged_locations_and_newer_plan_versions_fail(self):
        original = book(LEFT)
        with self.assertRaises(ValueError):
            plan_proofread(
                original, original, flagged=[{"member": "missing", "index": 0}]
            )
        plan = plan_proofread(original, original)
        plan["version"] = 99
        with self.assertRaisesRegex(ValueError, "version"):
            apply_plan(original, original, plan)

    def test_partial_note_image_mentions_are_reviewed_semantically(self):
        from src.content.proofread import completion_candidates

        original, reference = (
            book(LEFT, RIGHT, "作者有话说：", "已有解释"),
            book(LEFT, RIGHT),
        )
        original["chapters"]["one"]["blocks"].insert(2, {"kind": "divider", "runs": []})
        reference["chapters"]["one"]["source"] = {"id": "1"}
        evidence = {
            "chapters": {
                "1": {
                    "note_present": True,
                    "note_html": "已有解释<br>下面这张图是时间轴",
                }
            }
        }
        plan = plan_proofread(original, reference, reference_evidence=evidence)
        note = completion_candidates(plan)[0]
        self.assertEqual(note["missing_line_indices"], [1])
        decisions = {
            "fingerprint": plan["fingerprint"],
            "reviews": [
                {
                    "id": note["id"],
                    "verdict": "approved",
                    "insertions": [],
                    "reason": "Only points to an omitted image",
                }
            ],
        }
        candidate, ops = apply_plan(
            original, reference, plan, completion_decisions=decisions
        )
        self.assertEqual(candidate, original)
        self.assertFalse(ops)

    def test_existing_complete_note_gets_divider_without_rewriting_and_is_idempotent(
        self,
    ):
        original = book(LEFT, "", "作者有话要说：原书已有的说明")
        original["chapters"]["one"]["blocks"][-1]["runs"][0]["styles"] = ["bold"]
        reference = book(LEFT)
        plan = plan_proofread(original, reference)
        candidate, ops = apply_plan(original, reference, plan)
        self.assertEqual([op["kind"] for op in ops], ["insert_divider"])
        self.assertEqual(candidate["chapters"]["one"]["blocks"][-2]["kind"], "divider")
        self.assertEqual(
            candidate["chapters"]["one"]["blocks"][-1],
            original["chapters"]["one"]["blocks"][-1],
        )
        self.assertFalse(plan_proofread(candidate, reference)["operations"])
        # Existing separation through blank lines also counts; no duplicate line.
        candidate["chapters"]["one"]["blocks"].insert(-1, paragraph(""))
        self.assertFalse(missing_note_dividers(candidate["chapters"]["one"]["blocks"]))
        for texts in (
            (LEFT, "作者有话说："),
            ("作者有话说：整页都是作话",),
            (LEFT, "正文提到作者有话说：但不是标题"),
            (LEFT, "作者有话说 4000"),
        ):
            self.assertFalse(
                missing_note_dividers(book(*texts)["chapters"]["one"]["blocks"])
            )


class LocalWorkflowTests(unittest.TestCase):
    def test_cover_survives_prepare_and_apply_without_changing_source(self):
        from src.workflows.proofread import apply_proofread, prepare_proofread

        original = {
            "version": 3,
            "identifier": "fixture",
            "source_format": "epub",
            "metadata": metadata_defaults({"title": "封面保留"}),
            **book(LEFT, RIGHT),
        }
        reference = copy.deepcopy(original)
        reference["chapters"]["one"]["blocks"].insert(1, paragraph(""))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input/source.json"
            save_source(original, source, b"test-cover", "image/png")
            run = root / "run"
            save_source(reference, run / "reference/source.json")
            (run / "reference/evidence.json").write_text(
                json.dumps({"readable": 1, "total": 1})
            )
            with patch(
                "src.workflows.proofread.collect_reference",
                return_value=run / "reference/source.json",
            ):
                prepare_proofread(
                    run,
                    input_path=source,
                    jinjiang="1",
                    config_path=root / "config.json",
                )
            apply_proofread(run)
            candidate, cover, mime = load_prepared_source(run / "candidate.json")
            self.assertEqual((cover, mime), (b"test-cover", "image/png"))
            self.assertEqual(len(candidate["chapters"]["one"]["blocks"]), 3)
            self.assertEqual(load_prepared_source(source)[0], original)


class NativePatchTests(unittest.TestCase):
    def test_author_note_append_response_and_default_annotations(self):
        blocks = [
            {"kind": "divider", "runs": []},
            paragraph("作者有话说："),
            paragraph("你好"),
        ]
        payload = append_payload(blocks)
        ids = ["00000000-0000-4000-8000-00000000000" + str(i) for i in range(3)]
        response = {
            "object": "list",
            "results": [
                {**b, "id": id, "has_children": False} for b, id in zip(payload, ids)
            ],
            "has_more": False,
            "next_cursor": None,
        }
        after = [{"id": "", **b} for b in blocks]
        actual = acknowledge_append(response, [], after)
        self.assertEqual([b["id"] for b in actual], ids)
        self.assertTrue(native_equal(actual, after, new_ids=True))
        # An insertion may return the existing suffix as well as the new blocks.
        existing = {"id": "00000000-0000-4000-8000-000000000099", **paragraph("old")}
        response["results"].append({"id": existing["id"], "type": "paragraph"})
        self.assertEqual(acknowledge_append(response, [existing], after), actual)
        response["results"][1]["paragraph"]["rich_text"][0]["text"]["content"] = "wrong"
        with self.assertRaises(ValueError):
            acknowledge_append(response, [], after)

    def test_existing_styles_links_and_color_survive_text_patch(self):
        raw = {
            "type": "paragraph",
            "has_children": False,
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": "山 间",
                            "link": {"url": "https://example.org"},
                        },
                        "annotations": {"bold": True, "color": "red"},
                        "plain_text": "山 间",
                        "href": "https://example.org",
                    }
                ]
            },
        }
        payload = text_payload(raw, "山 间", "山间")
        run = payload["paragraph"]["rich_text"][0]
        self.assertEqual(
            run["text"], {"content": "山间", "link": {"url": "https://example.org"}}
        )
        self.assertEqual(run["annotations"], {"bold": True, "color": "red"})
        self.assertEqual(raw["paragraph"]["rich_text"][0]["text"]["content"], "山 间")


class WriteRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_divider_is_inserted_before_existing_note_and_read_back(self):
        original, reference = book(LEFT, "作者有话要说：已有的作话"), book(LEFT)
        candidate, ops = apply_plan(
            original, reference, plan_proofread(original, reference)
        )
        native = [
            {"id": str(i), **b}
            for i, b in enumerate(original["chapters"]["one"]["blocks"])
        ]
        evidence = {
            "work_id": "work",
            "discovery": {},
            "extras_source": "extras",
            "outline": [],
            "pages": {
                "one": {
                    "page_id": "page",
                    "data_source_id": "ds",
                    "title": "第一章",
                    "title_field": "章节",
                    "native": copy.deepcopy(native),
                }
            },
        }
        test = self

        class Reader:
            def __init__(self, *args, **kwargs):
                pass

            async def outline(self, *args, **kwargs):
                return []

            async def document(self, *args):
                return SimpleNamespace(
                    native=copy.deepcopy(native),
                    data_source_id="ds",
                    properties={"章节": "第一章"},
                )

        class Tools:
            async def call_api(self, request):
                test.assertEqual(
                    request["json"],
                    {
                        "after": "0",
                        "children": [
                            {"object": "block", "type": "divider", "divider": {}}
                        ],
                    },
                )
                added = "00000000-0000-4000-8000-000000000001"
                native.insert(1, {"id": added, "kind": "divider", "runs": []})
                return {
                    "status": 200,
                    "body": {
                        "object": "list",
                        "results": [
                            {
                                "id": added,
                                "object": "block",
                                "type": "divider",
                                "divider": {},
                                "has_children": False,
                            }
                        ],
                    },
                }

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.proofread.NotionBooks", Reader),
        ):
            result = await apply_edits(
                original,
                candidate,
                evidence,
                ops,
                Path(temp) / "journal.json",
                tools=Tools(),
            )
        self.assertTrue(result["verified"])
        self.assertEqual(
            [b["kind"] for b in native], ["paragraph", "divider", "paragraph"]
        )
        self.assertEqual(
            [b["id"] for b in native if b["kind"] != "divider"], ["0", "1"]
        )

    async def test_lost_append_response_resumes_without_duplicate_and_detects_conflict(
        self,
    ):
        original, reference = book(LEFT, RIGHT), book(LEFT, "", RIGHT)
        plan = plan_proofread(original, reference)
        candidate, ops = apply_plan(original, reference, plan)
        native = [{"id": "a", **paragraph(LEFT)}, {"id": "b", **paragraph(RIGHT)}]
        evidence = {
            "work_id": "work",
            "discovery": {},
            "extras_source": "extras",
            "outline": [],
            "pages": {
                "one": {
                    "page_id": "page",
                    "data_source_id": "ds",
                    "title": "第一章",
                    "title_field": "章节",
                    "native": copy.deepcopy(native),
                }
            },
        }

        class Reader:
            def __init__(self, *args, **kwargs):
                pass

            async def outline(self, *args, **kwargs):
                return []

            async def document(self, *args):
                return SimpleNamespace(
                    native=copy.deepcopy(native),
                    data_source_id="ds",
                    properties={"章节": "第一章"},
                )

        class Tools:
            writes = 0

            async def call_api(self, request):
                self.writes += 1
                native.insert(1, {"id": "inserted", "kind": "paragraph", "runs": []})
                raise TimeoutError("response lost after commit")

        tools = Tools()
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("src.notion.proofread.NotionBooks", Reader),
        ):
            journal = Path(temp) / "journal.json"
            with self.assertRaises(TimeoutError):
                await apply_edits(
                    original, candidate, evidence, ops, journal, tools=tools
                )
            result = await apply_edits(
                original, candidate, evidence, ops, journal, tools=tools
            )
            self.assertTrue(result["verified"])
            self.assertEqual(tools.writes, 1)
            self.assertEqual(len(native), 3)
            native[0]["runs"][0]["text"] += "编辑者修改"
            with self.assertRaisesRegex(ValueError, "changed"):
                await apply_edits(
                    original, candidate, evidence, ops, journal, tools=tools
                )


if __name__ == "__main__":
    unittest.main()
