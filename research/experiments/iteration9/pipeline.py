from __future__ import annotations

import argparse
from datetime import UTC, datetime
from functools import partial

from experiments.iteration6 import prompts as legacy
from experiments.iteration6.probe import binding, run_jobs
from experiments.iteration7.runtime import invoke as call, read, sha, write
from experiments.iteration9 import prompts as p
from experiments.iteration9.study import GENERATOR, REVIEWER, ROOT, prior, verify_manifest

invoke = partial(call, ROOT)


def apply_patches(paragraphs: list[str], patches: list[dict]) -> list[str]:
    """Resolve all exact spans against the original; never cascade guessed matches."""
    spans: dict[int, list[tuple[int, int, str]]] = {}
    for patch in patches:
        index, before, after = patch["paragraph_index"], patch["before"], patch["after"]
        if type(index) is not int or not 0 <= index < len(paragraphs):
            raise ValueError("Patch paragraph index outside input")
        if not isinstance(before, str) or not before or paragraphs[index].count(before) != 1:
            raise ValueError(f"Patch before must occur exactly once in paragraph {index}")
        if not isinstance(after, str) or not after.strip() or "\n" in after:
            raise ValueError("Patch after must be nonempty and stay inside one paragraph")
        start = paragraphs[index].index(before)
        spans.setdefault(index, []).append((start, start + len(before), after))
    result = list(paragraphs)
    for index, pieces in spans.items():
        ordered = sorted(pieces)
        if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
            raise ValueError(f"Overlapping patches in paragraph {index}")
        text = paragraphs[index]
        for start, end, after in reversed(ordered):
            text = text[:start] + after + text[end:]
        result[index] = text
    return result


def source_text(sample: dict) -> str:
    return "\n".join(sample["context_before"] + [x["english"] for x in sample["english"]] + sample["context_after"])


def validate_qa(sample: dict, paragraphs: list[str], result: dict) -> list[str]:
    for patch in result["patches"]:
        if not patch["english_support"] or patch["english_support"] not in source_text(sample):
            raise ValueError("QA support is not a literal English span")
    return apply_patches(paragraphs, result["patches"])


def exact_gold(payload: dict, result: dict) -> dict:
    lines = {x["line"]: x["text"] for x in payload["chinese_search_region"]}
    first, last = result["start_line"], result["end_line"]
    if not result["aligned"] or result["confidence"] != "high" or first not in lines or last not in lines or first > last:
        raise ValueError("Alignment requires confident in-range source lines")
    a, b = result["first_paragraph_quote"], result["last_paragraph_quote"]
    if not a or not b:
        raise ValueError("Empty alignment boundary")
    if first == last:
        if a != b or lines[first].count(a) != 1:
            raise ValueError("Single-line crop is not an exact unique substring")
    elif not lines[first].endswith(a) or not lines[last].startswith(b):
        raise ValueError("Boundary quotes must be exact suffix/prefix of source lines")
    chosen = [{"line": i, "text": text} for i, text in lines.items() if first <= i <= last]
    paragraphs, spans = [], []
    for row in chosen:
        text = row["text"]
        start = (text.index(a) if first == last else len(text) - len(a)) if row["line"] == first else 0
        end = start + len(a) if first == last else len(b) if row["line"] == last else len(text)
        paragraphs.append(text[start:end])
        spans.append({"line": row["line"], "start": start, "end": end})
    return {**result, "usable": True, "lines": chosen, "paragraphs": paragraphs, "literal_spans": spans}


def checked_call(name: str, prompt: str, payload: dict, schema: dict, model: str, validate) -> dict:
    result = invoke(name, prompt, payload, schema, model)
    try:
        validate(result)
    except ValueError as exc:
        write(ROOT / f"format_issues/{name}.json", {"error": str(exc), "original_result": result})
        repair_payload = {"original_input": payload, "invalid_result": result, "validation_error": str(exc)}
        result = invoke(name + "_format_repair", prompt + "\nRepair only the invalid literal span, boundary or indexing representation. Preserve proposed meaning and choices. This is a format/provenance retry, not an opportunity to seek a better-scoring output.", repair_payload, schema, model)
        validate(result)
    return result


def align(sid: str) -> None:
    payload = read(ROOT / f"alignment_inputs/{sid}.json")
    result = checked_call(f"align/{sid}", p.ALIGN_PRECISE, payload, p.ALIGN_PRECISE_SCHEMA, GENERATOR,
                          lambda value: exact_gold(payload, value))
    write(ROOT / f"gold/{sid}.json", exact_gold(payload, result))


def validate_text(result: dict) -> None:
    if not result["paragraphs"] or not all(isinstance(x, str) and x.strip() for x in result["paragraphs"]):
        raise ValueError("Empty translation paragraph")


def generate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    refs = read(prior.BANK_ROOT / "authentic_examples.json")
    refs = {**refs, "examples": [x for x in refs["examples"] if x["title"] != sample["title"]]}
    old_bank = read(prior.BANK_ROOT / "bank.json")["prompt_examples"]
    assert all(x["title"] != sample["title"] for x in old_bank)
    base = {"sample_id": sid, "book": sample["title"],
            "english": [{"index": x["index"], "english": x["english"]} for x in sample["english"]],
            "context_before_do_not_translate": sample["context_before"], "context_after_do_not_translate": sample["context_after"],
            "authentic_examples": refs}
    direct = checked_call(f"probe/{sid}/direct", legacy.DIRECT, base, legacy.TEXT_SCHEMA, GENERATOR, validate_text)
    write(ROOT / f"outputs/{sid}/direct.json", direct)
    old_edit = checked_call(f"probe/{sid}/old_editor", legacy.EDIT, {"paragraphs": direct["paragraphs"],
        "training_contrasts": [{"before": x["before"], "after": x["after"], "reason": x["reason"]} for x in old_bank]},
        legacy.TEXT_SCHEMA, GENERATOR, validate_text)
    write(ROOT / f"outputs/{sid}/old_editor.json", old_edit)
    old = checked_call(f"probe/{sid}/old_qa", legacy.QA, {"english": base["english"],
        "context_before_do_not_translate": sample["context_before"], "context_after_do_not_translate": sample["context_after"],
        "edited_chinese": old_edit}, legacy.TEXT_SCHEMA, REVIEWER, validate_text)
    write(ROOT / f"outputs/{sid}/old.json", old)

    bank = read(ROOT / "style_bank.json")
    cards = [c for c in bank["cards"] if c["title"] != sample["title"]]
    contexts = {sid: context for sid, context in bank["reference_contexts"].items() if context["title"] != sample["title"]}
    new_edit = checked_call(f"probe/{sid}/new_editor", p.EDIT,
        {"paragraphs": direct["paragraphs"], "style_cards": cards, "reference_contexts": contexts},
        p.EDIT_SCHEMA, GENERATOR, lambda value: apply_patches(direct["paragraphs"], value["patches"]))
    edited = apply_patches(direct["paragraphs"], new_edit["patches"])
    write(ROOT / f"stages/{sid}/new_editor_patches.json", new_edit)
    write(ROOT / f"outputs/{sid}/new_editor.json", {"paragraphs": edited})
    qa_payload = {"english_target": base["english"], "context_before": sample["context_before"],
                  "context_after": sample["context_after"], "paragraphs": edited}
    qa = checked_call(f"probe/{sid}/new_qa", p.QA, qa_payload, p.QA_SCHEMA, REVIEWER,
                      lambda value: validate_qa(sample, edited, value))
    write(ROOT / f"stages/{sid}/new_qa_proposals.json", qa)
    decisions = []
    if qa["patches"]:
        proposals = [{"proposal_index": i, "paragraph_index": x["paragraph_index"], "before": x["before"],
                      "after": x["after"], "english_support": x["english_support"]} for i, x in enumerate(qa["patches"])]
        def validate_decisions(result: dict) -> None:
            ids = [d["proposal_index"] for d in result["decisions"]]
            if sorted(ids) != list(range(len(proposals))):
                raise ValueError("Verification must cover every proposal exactly once")
        verified = checked_call(f"probe/{sid}/verify_qa", p.VERIFY_QA, {**qa_payload, "proposals": proposals},
                                p.VERIFY_SCHEMA, GENERATOR, validate_decisions)
        decisions = verified["decisions"]
    accepted = [qa["patches"][d["proposal_index"]] for d in decisions if d["accept"]]
    final = apply_patches(edited, accepted)
    write(ROOT / f"stages/{sid}/qa_decisions.json", {"decisions": decisions, "accepted_count": len(accepted)})
    write(ROOT / f"outputs/{sid}/new.json", {"paragraphs": final})
    write(ROOT / f"stages/{sid}/provenance.json", {"shared_direct_sha256": sha(ROOT / f"outputs/{sid}/direct.json"),
        "old_editor_sha256": sha(ROOT / f"outputs/{sid}/old_editor.json"), "new_editor_sha256": sha(ROOT / f"outputs/{sid}/new_editor.json"),
        "old_final_sha256": sha(ROOT / f"outputs/{sid}/old.json"), "new_final_sha256": sha(ROOT / f"outputs/{sid}/new.json"),
        "final_texts_identical": old["paragraphs"] == final, "style_card_ids": [c["card_id"] for c in cards]})


def evaluate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    mapping = read(ROOT / "blind_mapping.json")[sid]
    methods = list(reversed(list(mapping.values())))
    candidates = [{"candidate_id": f"R{i + 1}", "paragraphs": read(ROOT / f"outputs/{sid}/{m}.json")["paragraphs"]}
                  for i, m in enumerate(methods)]
    def validate(result: dict) -> None:
        ids = [a["candidate_id"] for a in result["assessments"]]
        if sorted(ids) != ["R1", "R2"]:
            raise ValueError("Both anonymous candidates must be assessed")
    result = checked_call(f"evaluation/{sid}", p.FINAL_AUDIT,
        {"english": sample["english"], "context_before": sample["context_before"], "context_after": sample["context_after"],
         "candidates": candidates}, p.SOURCE_SCHEMA, REVIEWER, validate)
    write(ROOT / f"evaluations/{sid}.json", {"mapping": {c["candidate_id"]: m for c, m in zip(candidates, methods)},
        "result": result, "interpretation": "Anonymous source-only model concerns, not human votes or a style winner. Outputs remain frozen regardless of concerns."})


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
        assert len(list((ROOT / "outputs").glob("*/new.json"))) == 48
        assert len(list((ROOT / "evaluations").glob("*.json"))) == 48
        paths = [p for folder in ("gold", "outputs", "stages", "evaluations", "calls", "requests", "format_issues")
                 for p in (ROOT / folder).rglob("*.json")]
        write(ROOT / "output_manifest.json", {"frozen_at": datetime.now(UTC).isoformat(),
              "bindings": binding(paths + [ROOT / "manifest.json", ROOT / "blind_mapping.json"])})
    verify_manifest(ROOT / "output_manifest.json")
    print("Paired outputs and independent evaluations frozen", flush=True)


if __name__ == "__main__":
    main()
