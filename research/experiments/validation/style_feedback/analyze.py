from __future__ import annotations

import itertools
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from experiments.iteration6.probe import binding
from experiments.iteration8 import study
from experiments.iteration7.runtime import read, write
from experiments.validation.style_feedback.evaluate import DIMENSIONS, ROOT, verify


def paragraphs_text(value: list) -> str:
    return "\n".join(item if isinstance(item, str) else item["english"] for item in value)


def validate_rating(payload: dict, result: dict) -> dict:
    texts = {c["candidate_id"]: paragraphs_text(c["paragraphs"]) for c in payload["candidates"]}
    ids = set(texts)
    assessments = [a["candidate_id"] for a in result["assessments"]]
    ranked = [cid for tier in result["ranking"] for cid in tier]
    errors = []
    if set(assessments) != ids or len(assessments) != len(ids):
        errors.append("assessment coverage")
    if set(ranked) != ids or len(ranked) != len(ids) or any(not tier for tier in result["ranking"]):
        errors.append("ranking coverage")
    for a in result["assessments"]:
        if not set(a["not_assessable_dimensions"]) <= set(DIMENSIONS):
            errors.append("unknown unassessable dimension")
        if set(a["scores"]) != set(DIMENSIONS) or any(type(x) is not int or not 1 <= x <= 5 for x in a["scores"].values()):
            errors.append("score domain")
    target = paragraphs_text(payload["english_target"])
    before = paragraphs_text(payload["english_context_before"])
    after = paragraphs_text(payload["english_context_after"])
    english = "\n".join((before, target, after))
    author = paragraphs_text(payload["author_chinese"])
    units = []
    for unit in result["units"]:
        problems = []
        quoted_ids = [c["candidate_id"] for c in unit["candidates"]]
        if set(quoted_ids) != ids or len(quoted_ids) != len(ids):
            problems.append("candidate coverage")
        for label, quote, source in (("english", unit["english_quote"], english), ("author", unit["author_quote"], author)):
            if quote and quote not in source:
                problems.append(f"non-exact {label} quote")
            if not quote and unit["classification"] == "comparable_style":
                problems.append(f"missing {label} quote for comparable unit")
        for c in unit["candidates"]:
            if c["candidate_id"] not in texts or (c["quote"] and c["quote"] not in texts[c["candidate_id"]]):
                problems.append(f"non-exact {c['candidate_id']} quote")
            if not c["quote"] and unit["classification"] == "comparable_style":
                problems.append(f"missing {c['candidate_id']} quote for comparable unit")
        units.append({"unit_id": unit["unit_id"], "classification": unit["classification"],
                      "problems": problems, "english_context_only": bool(unit["english_quote"] and unit["english_quote"] in english and unit["english_quote"] not in target),
                      "exact_comparable": unit["classification"] == "comparable_style" and not problems})
    return {"structural_errors": errors, "units": units,
            "exact_comparable_units": sum(u["exact_comparable"] for u in units)}


def expand_rating(result: dict, identities: dict) -> dict:
    tiers = {cid: i for i, tier in enumerate(result["ranking"]) for cid in tier}
    expanded = {}
    for a in result["assessments"]:
        available = {d: v for d, v in a["scores"].items() if d not in a["not_assessable_dimensions"]}
        for method in identities[a["candidate_id"]]:
            expanded[method] = {"mean": statistics.mean(available.values()) if available else None,
                                "dimensions": available, "tier": tiers[a["candidate_id"]]}
    return expanded


def summarize(records: list[dict]) -> dict:
    scores = {}
    for method in study.METHODS:
        by_book = {}
        for title in study.TITLES:
            values = [r["methods"][method]["mean"] for r in records if r["title"] == title and r["methods"][method]["mean"] is not None]
            by_book[title] = statistics.mean(values) if values else None
        available = [v for v in by_book.values() if v is not None]
        scores[method] = {"book_equal_mean": statistics.mean(available) if available else None,
                          "by_book": by_book, "dimensions": {}}
        for dim in DIMENSIONS:
            dim_books = []
            for title in study.TITLES:
                values = [r["methods"][method]["dimensions"][dim] for r in records if r["title"] == title and dim in r["methods"][method]["dimensions"]]
                if values:
                    dim_books.append(statistics.mean(values))
            scores[method]["dimensions"][dim] = statistics.mean(dim_books) if dim_books else None
    comparisons = {}
    for a, b in itertools.combinations(study.METHODS, 2):
        counts = Counter({"a_closer": 0, "tie": 0, "b_closer": 0})
        for r in records:
            x, y = r["methods"][a]["tier"], r["methods"][b]["tier"]
            counts["a_closer" if x < y else "b_closer" if y < x else "tie"] += 1
        comparisons[f"{a}_vs_{b}"] = dict(counts)
    return {"review_count": len(records), "scores": scores, "pairwise": comparisons,
            "top_tier_counts": {m: sum(r["methods"][m]["tier"] == 0 for r in records) for m in study.METHODS}}


def human_agreement(records: list[dict], human: dict, exclude: set[str]) -> dict:
    votes = {r["sample_id"]: r for r in human["rows"] if r["choice"] == "preferred" and r["sample_id"] not in exclude}
    matched = [r for r in records if r["sample_id"] in votes]
    strict, tie, absent = [], [], []
    for r in matched:
        chosen = votes[r["sample_id"]]["methods"][0]
        top = [m for m in study.METHODS if r["methods"][m]["tier"] == 0]
        (strict if top == [chosen] else tie if chosen in top else absent).append(r["sample_id"])
    return {"n": len(matched), "same_single_winner": strict, "human_choice_in_model_tied_top": tie, "human_choice_not_top": absent}


def main() -> None:
    manifest = verify(ROOT / "manifest.json")
    verify(ROOT / "ratings_manifest.json")
    identities, human = read(ROOT / "identities.json"), read(ROOT / "human_summary.json")
    records, validation = [], []
    for job in manifest["jobs"]:
        sid, reviewer = job["sample_id"], job["reviewer"]
        payload = read(ROOT / job["input"])
        result = read(ROOT / f"ratings/{sid}/{reviewer}.json")
        checks = validate_rating(payload, result)
        validation.append({"sample_id": sid, "reviewer": reviewer, **checks})
        if checks["structural_errors"]:
            continue
        sample = read(study.ROOT / f"samples/{sid}.json")
        records.append({"sample_id": sid, "reviewer": reviewer, "title": sample["title"],
                        "methods": expand_rating(result, identities[sid]),
                        "exact_comparable_units": checks["exact_comparable_units"],
                        "all_units_exact": not any(u["problems"] for u in checks["units"])})
    write(ROOT / "quote_validation.json", validation)
    write(ROOT / "expanded_ratings.json", records)
    summary = {"created_at": datetime.now(UTC).isoformat(), "all": summarize(records), "by_reviewer": {},
               "evidence_supported_sensitivity": summarize([r for r in records if r["exact_comparable_units"]]),
               "fully_exact_evidence_sensitivity": summarize([r for r in records if r["all_units_exact"] and r["exact_comparable_units"]]),
               "structural_failures": sum(bool(v["structural_errors"]) for v in validation),
               "unit_count": sum(len(v["units"]) for v in validation),
               "units_with_quote_or_coverage_problems": sum(bool(u["problems"]) for v in validation for u in v["units"]),
               "context_only_units": sum(u["english_context_only"] for v in validation for u in v["units"]),
               "reviews_without_exact_comparable_units": sum(not v["exact_comparable_units"] for v in validation)}
    for reviewer in ("sol", "terra"):
        rows = [r for r in records if r["reviewer"] == reviewer]
        summary["by_reviewer"][reviewer] = {**summarize(rows),
            "human_agreement": human_agreement(rows, human, set()),
            "human_agreement_excluding_user_examples": human_agreement(rows, human, {"balanced_016", "balanced_017", "balanced_018"})}
    disagreements = []
    by_key = {(r["sample_id"], r["reviewer"]): r for r in records}
    for sid in identities:
        a, b = by_key.get((sid, "sol")), by_key.get((sid, "terra"))
        if a and b:
            top_a = {m for m in study.METHODS if a["methods"][m]["tier"] == 0}
            top_b = {m for m in study.METHODS if b["methods"][m]["tier"] == 0}
            disagreements.append({"sample_id": sid, "top_exact_agreement": top_a == top_b,
                                   "top_overlap": bool(top_a & top_b), "sol": sorted(top_a), "terra": sorted(top_b)})
    summary["reviewer_top_agreement"] = {"n": len(disagreements),
        "exact": sum(x["top_exact_agreement"] for x in disagreements),
        "overlap": sum(x["top_overlap"] for x in disagreements), "rows": disagreements}
    summary["interpretation"] = "Descriptive ordinal judgments, 48 scene clusters / six books / two model readings. Reversed order is confounded with reviewer; it does not isolate order bias. Exact quote checks validate provenance, not the reasoning. Human overlap is post-hoc partial feedback, not an independent validated style metric."
    write(ROOT / "analysis.json", summary)
    write(ROOT / "analysis_manifest.json", {"bindings": binding([ROOT / "manifest.json", ROOT / "ratings_manifest.json",
        ROOT / "analysis.json", ROOT / "quote_validation.json", ROOT / "expanded_ratings.json", Path(__file__)])})
    print({"reviews": len(records), "structural_failures": summary["structural_failures"], "quote_problem_units": summary["units_with_quote_or_coverage_problems"]})


if __name__ == "__main__":
    main()
