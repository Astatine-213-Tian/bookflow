from __future__ import annotations

import copy
import unittest

from tests.notion_api import roundtrip

from src.content.quote_review import apply_quote_review, find_quote_candidates
from src.inputs.html import read_html_blocks


def source(markup: str):
    hints = {}
    blocks = read_html_blocks(
        (
            "<html><head><style>p {text-align:justify}.inset {width:70%;font-size:.9em;color:brown}</style></head><body>"
            + markup
            + "</body></html>"
        ).encode(),
        "chapter.xhtml",
        {},
        evidence=hints,
    )
    return {
        "chapters": {"one": {"title": "测试篇目", "blocks": blocks}},
        "extras": [],
    }, {"one": [hints.get(i, {}) for i in range(len(blocks))]}


class QuoteReviewTests(unittest.TestCase):
    def test_styled_quote_is_a_candidate_until_codex_confirms_it(self):
        book, evidence = source(
            '<p>作者的议论。</p><p>正如读者所说：</p><p class="inset">“这是引用的评论。”</p><p>接着讨论。</p>'
        )
        before = copy.deepcopy(book)
        request = find_quote_candidates(book, evidence)
        self.assertEqual(len(request["candidates"]), 1)
        candidate = request["candidates"][0]
        self.assertEqual(candidate["index"], 2)
        self.assertIn("所说", candidate["before"][-1])
        self.assertEqual(candidate["source"]["style"]["width"], "70%")
        self.assertEqual(book, before)
        decisions = {
            "fingerprint": request["fingerprint"],
            "reviews": [
                {
                    "id": candidate["id"],
                    "verdict": "quote",
                    "confidence": "high",
                    "reason": "明确引述他人评论，且为单独的缩进段落。",
                }
            ],
        }
        result, report = apply_quote_review(book, request, decisions)
        self.assertEqual(result["chapters"]["one"]["blocks"][2]["kind"], "quote")
        self.assertEqual(report["applied"], 1)
        for old, new in zip(
            before["chapters"]["one"]["blocks"], result["chapters"]["one"]["blocks"]
        ):
            self.assertEqual(old["runs"], new["runs"])
        block = copy.deepcopy(result["chapters"]["one"]["blocks"][2])
        block.pop("alignment", None)
        self.assertEqual(roundtrip([block])[0]["kind"], "quote")

    def test_keep_uncertain_and_ordinary_dialogue_do_not_change_content(self):
        book, evidence = source(
            '<p>“走吧。”</p><p>“好。”</p><p class="inset">特殊排版未必是引用。</p><p>普通正文。</p>'
        )
        request = find_quote_candidates(book, evidence)
        self.assertEqual([x["index"] for x in request["candidates"]], [2])
        for verdict, confidence in [
            ("keep", "high"),
            ("uncertain", "low"),
            ("quote", "medium"),
        ]:
            decisions = {
                "fingerprint": request["fingerprint"],
                "reviews": [
                    {
                        "id": request["candidates"][0]["id"],
                        "verdict": verdict,
                        "confidence": confidence,
                        "reason": "需要结合上下文。",
                    }
                ],
            }
            result, _ = apply_quote_review(book, request, decisions)
            self.assertEqual(result, book)

    def test_stale_missing_duplicate_and_text_rewrites_are_rejected(self):
        book, evidence = source(
            '<p>前文。</p><p class="inset">“评论。”</p><p>后文。</p>'
        )
        request = find_quote_candidates(book, evidence)
        row = {
            "id": request["candidates"][0]["id"],
            "verdict": "quote",
            "confidence": "high",
            "reason": "引文。",
        }
        for rows, fingerprint in [
            ([], request["fingerprint"]),
            ([row, row], request["fingerprint"]),
            ([row | {"text": "改写"}], request["fingerprint"]),
            ([row], "stale"),
        ]:
            with self.assertRaises(ValueError):
                apply_quote_review(
                    book, request, {"fingerprint": fingerprint, "reviews": rows}
                )
        changed = copy.deepcopy(book)
        changed["chapters"]["one"]["blocks"][0]["runs"][0]["text"] = "新上下文。"
        with self.assertRaises(ValueError):
            apply_quote_review(
                changed,
                request,
                {"fingerprint": request["fingerprint"], "reviews": [row]},
            )

    def test_review_workflow_resumes_without_repeating_model_calls(self):
        import json, tempfile
        from pathlib import Path
        from src.workflows.quote_review import review_quotes

        book, evidence = source(
            '<p>正如读者所说：</p><p class="inset">“引文。”</p><p>后文。</p>'
        )
        calls = []

        def runner(prompt):
            calls.append(prompt)
            candidates = json.loads(prompt.split("\n\n", 1)[1])
            return json.dumps(
                {
                    "reviews": [
                        {
                            "id": c["id"],
                            "verdict": "quote",
                            "confidence": "high",
                            "reason": "Explicit attribution.",
                        }
                        for c in candidates
                    ]
                }
            )

        with tempfile.TemporaryDirectory() as d:
            one, report = review_quotes(book, evidence, Path(d), runner=runner)
            two, _ = review_quotes(
                book,
                evidence,
                Path(d),
                runner=lambda _: self.fail("cached decision called model"),
            )
            self.assertEqual(one, two)
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["applied"], 1)
            untouched, _ = source("<p>Ordinary prose.</p>")
            result, report = review_quotes(
                untouched,
                None,
                Path(d) / "plain",
                runner=lambda _: self.fail("no candidates called model"),
            )
            self.assertEqual(result, untouched)
            self.assertEqual(report["candidates"], 0)
