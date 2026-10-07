"""Run or reuse bounded Codex judgments before content normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.content.quote_review import (
    apply_quote_review,
    find_quote_candidates,
    quote_review_prompt,
    review_fingerprint,
)
from src.runtime.codex_review import extract_review_payload, run_review_prompt
from src.runtime.files import write_json


def review_quotes(
    book: dict,
    evidence: dict | None,
    run_dir: Path,
    *,
    decisions: dict | None = None,
    runner: Callable[[str], str] | None = None,
) -> tuple[dict, dict]:
    request = find_quote_candidates(book, evidence)
    write_json(run_dir / "quote-candidates.json", request)
    if not request["candidates"]:
        if decisions is not None:
            return apply_quote_review(book, request, decisions)
        return book, {"candidates": 0, "applied": 0, "unresolved": 0, "decisions": []}
    cache = run_dir / "quote-decisions.json"
    if decisions is None and cache.exists():
        saved = json.loads(cache.read_text())
        if saved.get("fingerprint") == request["fingerprint"]:
            decisions = saved
    if decisions is None:
        run = runner or (lambda prompt: run_review_prompt(prompt, 300))
        rows = []
        candidates = request["candidates"]
        for start in range(0, len(candidates), 8):
            batch = candidates[start : start + 8]
            batch_path = run_dir / "quote-review-batches" / f"{start:04d}.json"
            if batch_path.exists():
                saved = json.loads(batch_path.read_text())
            else:
                saved = {}
            if saved.get("fingerprint") == request["fingerprint"]:
                batch_rows = saved["reviews"]
            else:
                payload = extract_review_payload(
                    run(quote_review_prompt({"candidates": batch}))
                )
                if set(payload) != {"reviews"}:
                    raise ValueError("Codex quote review returned unexpected fields")
                batch_rows = payload["reviews"]
            # Validate each batch before caching it, including exact IDs and coverage.
            batch_request = {
                "source_fingerprint": request["source_fingerprint"],
                "candidates": batch,
            }
            batch_request = {
                "fingerprint": review_fingerprint(batch_request),
                **batch_request,
            }
            apply_quote_review(
                book,
                batch_request,
                {"fingerprint": batch_request["fingerprint"], "reviews": batch_rows},
            )
            write_json(
                batch_path,
                {"fingerprint": request["fingerprint"], "reviews": batch_rows},
            )
            rows.extend(batch_rows)
        decisions = {"fingerprint": request["fingerprint"], "reviews": rows}
    result, report = apply_quote_review(book, request, decisions)
    write_json(cache, decisions)
    write_json(run_dir / "quote-review.json", report)
    return result, report
