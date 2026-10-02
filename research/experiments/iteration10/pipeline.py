from __future__ import annotations

import argparse
from datetime import UTC, datetime
from functools import partial

from experiments.iteration6.probe import binding, run_jobs
from experiments.iteration7.runtime import invoke as call, read, sha, write
from experiments.iteration9.pipeline import exact_gold, validate_text
from experiments.iteration10 import prompts as p
from experiments.iteration10.study import GENERATOR, METHODS, REVIEWER, ROOT, prior, verify_manifest

invoke = partial(call, ROOT)


def generation_packets(sample: dict, references: dict, bank: list[dict]) -> dict:
    """The earlier direct/positive payloads, with identical leave-book-out inputs."""
    refs = {**references, "examples": [x for x in references["examples"] if x["title"] != sample["title"]]}
    assert all(x["title"] != sample["title"] for x in bank)
    base = {"sample_id": sample["sample_id"], "book": sample["title"],
            "english": [{"index": x["index"], "english": x["english"]} for x in sample["english"]],
            "context_before_do_not_translate": sample["context_before"],
            "context_after_do_not_translate": sample["context_after"], "authentic_examples": refs}
    positive = [{"english_context": x["english_support"], "corrected_chinese_fragment": x["after"]} for x in bank]
    return {"direct": (p.DIRECT, base), "positive": (p.DIRECT + p.POSITIVE, {**base, "wording_examples": positive})}


def align(sid: str) -> None:
    payload = read(ROOT / f"alignment_inputs/{sid}.json")
    result = invoke(f"align/{sid}", p.ALIGN_PRECISE, payload, p.ALIGN_PRECISE_SCHEMA, GENERATOR)
    # Substantive uncertainty must remain visible; it is never a format retry.
    if not result["aligned"] or result["confidence"] != "high":
        write(ROOT / f"alignment_review/{sid}.json", {"reason": "substantive alignment uncertainty", "result": result})
        raise ValueError(f"{sid}: independent source review required")
    try:
        gold = exact_gold(payload, result)
    except ValueError as exc:
        write(ROOT / f"format_issues/align/{sid}.json", {"error": str(exc), "original_result": result})
        repaired = invoke(f"align/{sid}_format_repair", p.ALIGN_PRECISE +
            "\nRepair literal boundary representation only. Preserve aligned/confidence/start_line/end_line exactly; do not pick a different passage.",
            {"original_input": payload, "invalid_result": result, "validation_error": str(exc)}, p.ALIGN_PRECISE_SCHEMA, GENERATOR)
        if any(repaired[k] != result[k] for k in ("aligned", "confidence", "start_line", "end_line")):
            raise ValueError(f"{sid}: alignment retry changed substantive selection")
        gold = exact_gold(payload, repaired)
    write(ROOT / f"gold/{sid}.json", gold)


def generate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    refs = read(prior.BANK_ROOT / "authentic_examples.json")
    bank = read(prior.BANK_ROOT / "bank.json")["prompt_examples"]
    packets = generation_packets(sample, refs, bank)
    for method in METHODS:
        prompt, payload = packets[method]
        result = invoke(f"probe/{sid}/{method}", prompt, payload, p.TEXT_SCHEMA, GENERATOR)
        validate_text(result)
        write(ROOT / f"outputs/{sid}/{method}.json", result)
    write(ROOT / f"provenance/{sid}.json", {"sample_sha256": sha(ROOT / f"samples/{sid}.json"),
        "output_sha256": {m: sha(ROOT / f"outputs/{sid}/{m}.json") for m in METHODS},
        "post_generation_editing": False,
        "final_texts_identical": read(ROOT / f"outputs/{sid}/direct.json")["paragraphs"] == read(ROOT / f"outputs/{sid}/positive.json")["paragraphs"]})


def evaluate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    methods = list(reversed(list(read(ROOT / "blind_mapping.json")[sid].values())))
    candidates = [{"candidate_id": f"R{i + 1}", "paragraphs": read(ROOT / f"outputs/{sid}/{m}.json")["paragraphs"]}
                  for i, m in enumerate(methods)]
    result = invoke(f"evaluation/{sid}", p.FINAL_AUDIT,
        {"english": sample["english"], "context_before": sample["context_before"],
         "context_after": sample["context_after"], "candidates": candidates}, p.SOURCE_SCHEMA, REVIEWER)
    if sorted(a["candidate_id"] for a in result["assessments"]) != ["R1", "R2"]:
        raise ValueError(f"{sid}: both anonymous candidates must be assessed once")
    write(ROOT / f"evaluations/{sid}.json", {"mapping": {c["candidate_id"]: m for c, m in zip(candidates, methods)},
        "result": result, "interpretation": "Read-only anonymous source audit. Model concerns are not confirmed errors or a style winner; no candidate is repaired or selected using this evaluation."})


def process(sid: str) -> None:
    align(sid)
    generate(sid)
    evaluate(sid)
    print(f"READY {sid}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    manifest = verify_manifest(ROOT / "manifest.json")
    if not (ROOT / "output_manifest.json").exists():
        run_jobs(process, [x["sample_id"] for x in manifest["draws"]], args.workers)
        assert len(list((ROOT / "outputs").glob("*/positive.json"))) == 48
        assert len(list((ROOT / "evaluations").glob("*.json"))) == 48
        paths = [path for folder in ("gold", "outputs", "provenance", "evaluations", "calls", "requests", "format_issues", "alignment_review")
                 for path in (ROOT / folder).rglob("*.json")]
        write(ROOT / "output_manifest.json", {"frozen_at": datetime.now(UTC).isoformat(),
            "bindings": binding(paths + [ROOT / "manifest.json", ROOT / "blind_mapping.json"])})
    verify_manifest(ROOT / "output_manifest.json")
    print("Direct/positive outputs and read-only evaluations frozen", flush=True)


if __name__ == "__main__":
    main()
