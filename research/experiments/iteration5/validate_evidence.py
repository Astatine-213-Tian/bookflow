from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.iteration5 import pilot


ROOT = pilot.ROOT
PLACEHOLDERS = re.compile(
    r"\[(?:未翻译|待翻译|翻译失败|TODO|TRANSLATION MISSING)\]"
    r"|<empty-block\s*/>|作为(?:一个)?\s*AI|I (?:cannot|can't) (?:translate|assist with|provide)",
    re.IGNORECASE,
)


def digest(value: Any) -> str:
    # Match the frozen pilot.invoke packet serialization exactly.
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def schema_errors(value: Any, schema: dict[str, Any], where: str = "result") -> list[str]:
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": type(value) is int}
    if kind in valid and not valid[kind]:
        return [f"{where}: expected {kind}"]
    errors: list[str] = []
    if kind == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: missing {key}")
        if schema.get("additionalProperties") is False:
            errors += [f"{where}: unexpected {key}" for key in value if key not in props]
        for key in value.keys() & props.keys():
            errors += schema_errors(value[key], props[key], f"{where}.{key}")
    elif kind == "array":
        for index, item in enumerate(value):
            errors += schema_errors(item, schema.get("items", {}), f"{where}[{index}]")
    elif kind == "integer":
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            errors.append(f"{where}: integer outside range")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: value outside enum")
    return errors


def paragraph_errors(value: Any, expected_count: int | None = None) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["paragraphs must be a nonempty array"]
    errors = []
    if expected_count is not None and len(value) != expected_count:
        errors.append(f"paragraph count {len(value)} differs from expected {expected_count}")
    for index, text in enumerate(value):
        if not isinstance(text, str) or not text.strip():
            errors.append(f"paragraph {index} is not a nonempty string")
        elif PLACEHOLDERS.search(text):
            errors.append(f"paragraph {index} contains a placeholder/refusal marker; manual source review required")
    return errors


def ledger_errors(value: Any, expected_ids: list[int]) -> tuple[list[str], list[str]]:
    errors = schema_errors(value, pilot.LEDGER_SCHEMA)
    warnings: list[str] = []
    if errors:
        return errors, warnings
    if not value["beats"]:
        return ["ledger has no beats"], warnings
    observed: list[int] = []
    allowed = set(expected_ids)
    for index, beat in enumerate(value["beats"]):
        ids = beat["source_ids"]
        if not ids:
            errors.append(f"beat {index} has no source IDs")
        if any(i not in allowed for i in ids):
            errors.append(f"beat {index} has out-of-range source IDs")
        if ids != sorted(ids):
            warnings.append(f"beat {index} source IDs are unsorted")
        if not any(beat[k].strip() for k in ("content_zh", "speech_zh", "discourse_zh")):
            errors.append(f"beat {index} has no content")
        observed.extend(ids)
    if sorted(set(observed)) != expected_ids:
        errors.append("ledger union does not exactly cover source IDs")
    # Repeating a paragraph across adjacent beats is permitted. Backtracking is reviewed.
    compact = [item for i, item in enumerate(observed) if i == 0 or item != observed[i - 1]]
    if compact != sorted(compact):
        warnings.append("beat source sequence backtracks; review before admission")
    return errors, warnings


def judgment_errors(value: Any, expected_ids: list[str]) -> list[str]:
    errors = schema_errors(value, pilot.RATING_SCHEMA)
    if errors:
        return errors
    if sorted(row["candidate_id"] for row in value["ratings"]) != sorted(expected_ids):
        errors.append("ratings do not cover candidate IDs exactly once")
    groups = value["style_ranking"]
    if any(not group for group in groups):
        errors.append("style ranking contains an empty tie group")
    if sorted(item for group in groups for item in group) != sorted(expected_ids):
        errors.append("style ranking does not cover candidate IDs exactly once")
    return errors


class Audit:
    def __init__(self, *, root: Path, allow_missing: bool) -> None:
        self.root = root
        self.allow_missing = allow_missing
        self.failures: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self.diagnostics: list[dict[str, Any]] = []
        self.missing: list[str] = []
        self.input_hashes: dict[str, str] = {}

    def fail(self, where: str, message: str) -> None:
        self.failures.append({"path": where, "message": message})

    def get(self, relative: str) -> Any | None:
        path = self.root / relative
        if not path.exists():
            self.missing.append(relative)
            return None
        self.input_hashes[relative] = pilot.sha(path)
        try:
            return pilot.read(path)
        except (ValueError, OSError) as exc:
            self.fail(relative, f"unreadable JSON: {type(exc).__name__}")
            return None

    def check(self, where: str, errors: list[str]) -> None:
        for error in errors:
            self.fail(where, error)

    def call(self, name: str, packet: dict[str, Any]) -> Any | None:
        requested = self.get(f"requests/{name}.json")
        called = self.get(f"calls/{name}.json")
        if requested is not None and requested != packet:
            self.fail(name, "stored request differs from independently reconstructed packet")
        if called is None:
            return None
        if called.get("input_sha256") != digest(packet):
            self.fail(name, "call input hash differs from reconstructed packet")
        if called.get("model") != packet["model"]:
            self.fail(name, "call model differs from frozen model")
        result = called.get("result")
        self.check(name, schema_errors(result, packet["schema"]))
        return result


def packet(prompt: str, payload: Any, schema: dict[str, Any], model: str) -> dict[str, Any]:
    return {"prompt": prompt, "payload": payload, "schema": schema, "model": model}


def check_generation(audit: Audit, manifest: dict[str, Any]) -> dict[str, str]:
    examples = audit.get("real_parallel_examples.json")
    hashes: dict[str, str] = {}
    for sid, *_ in manifest["scenes"]:
        sample = audit.get(f"samples/{sid}.json")
        if sample is None or examples is None:
            continue
        english = sample["english"]
        expected_ids = [row["index"] for row in english]
        base = {"sample_id": sid, "english": english, "glossary": pilot.TERMS}
        neutral_payload = {"pass": "semantic_draft", "book_title": "", "author": "",
            "source_context": "English published translation is semantic authority.",
            "chapter_id": sid, "chapter_title": "",
            "glossary": [{"source": k, "zh": v} for k, v in pilot.TERMS.items()],
            "sentence_translations": [], "items": [
                {**row, "current_zh": "", "context_before": [x["english"] for x in english[max(0, i-5):i]],
                 "context_after": [x["english"] for x in english[i+1:i+6]], "glossary_matches": []}
                for i, row in enumerate(english)]}
        neutral_rows: list[dict[str, Any]] = []
        for offset in range(0, len(english), 30):
            chunk = {**neutral_payload, "items": neutral_payload["items"][offset:offset+30]}
            part = audit.call(f"{sid}/neutral_{offset}", packet(pilot.build_translation_prompt(chunk), {},
                pilot.NEUTRAL_SCHEMA, manifest["generator_model"]))
            if part is not None and not schema_errors(part, pilot.NEUTRAL_SCHEMA):
                neutral_rows.extend(part["translations"])
        direct = audit.call(f"{sid}/direct", packet(pilot.DIRECT,
            {**base, "authentic_examples": examples}, pilot.TEXT_SCHEMA, manifest["generator_model"]))
        ledger = audit.call(f"{sid}/ledger", packet(pilot.LEDGER, base,
            pilot.LEDGER_SCHEMA, manifest["generator_model"]))
        checked = None
        rendered = None
        if ledger is not None:
            checked = audit.call(f"{sid}/ledger_qa", packet(pilot.LEDGER_QA,
                {**base, "ledger": ledger}, pilot.LEDGER_SCHEMA, manifest["judge_models"][1]))
        for label, value in (("ledger", ledger), ("ledger_qa", checked)):
            if value is None:
                continue
            errors, warnings = ledger_errors(value, expected_ids)
            if label == "ledger":
                audit.diagnostics.append({"path": f"{sid}/{label}", "intermediate_errors": errors,
                                          "intermediate_warnings": warnings,
                                          "admission_role": "Superseded by independently corrected ledger_qa."})
                continue
            audit.check(f"{sid}/{label}", errors)
            audit.warnings.extend({"id": f"{sid}/{label}/{i}", "path": f"{sid}/{label}", "message": warning}
                                  for i, warning in enumerate(warnings))
        if checked is not None:
            rendered = audit.call(f"{sid}/render", packet(pilot.RENDER,
                {"sample_id": sid, "glossary": pilot.TERMS, "content_ledger": checked,
                 "authentic_examples": examples}, pilot.TEXT_SCHEMA, manifest["generator_model"]))
        for method in manifest["methods"]:
            rel = f"outputs/{sid}/{method}.json"
            output = audit.get(rel)
            if output is None:
                continue
            if not isinstance(output, dict):
                audit.fail(rel, "output is not an object")
                continue
            audit.check(rel, paragraph_errors(output.get("paragraphs"), len(english) if method in {"neutral", "method4"} else None))
            hashes[rel] = audit.input_hashes[rel]
            if method == "neutral" and len(neutral_rows) == len(english):
                if [row["index"] for row in neutral_rows] != expected_ids:
                    audit.fail(rel, "neutral source IDs differ")
                if [row["zh"] for row in neutral_rows] != output.get("paragraphs"):
                    audit.fail(rel, "neutral output differs from raw call results")
            elif method in {"direct_scene", "ledger_scene"}:
                raw = direct if method == "direct_scene" else rendered
                if raw is not None and output != raw:
                    audit.fail(rel, "output differs from raw generation result")
            elif method == "method4":
                blocks = []
                for offset in range(0, len(english), 12):
                    block = audit.get(f"method4/{sid}/block_{offset}.json")
                    if block is not None:
                        audit.check(f"{sid}/method4/{offset}", paragraph_errors(block.get("paragraphs"), min(12, len(english)-offset)))
                        blocks.extend(block.get("paragraphs", []))
                if blocks != output.get("paragraphs"):
                    audit.fail(rel, "Method4 output differs from ordered saved block results")
    wanted = {f"outputs/{sid}/{method}.json" for sid, *_ in manifest["scenes"] for method in manifest["methods"]}
    actual = {str(p.relative_to(audit.root)) for p in (audit.root / "outputs").rglob("*.json")}
    for extra in sorted(actual - wanted):
        audit.fail(extra, "unexpected candidate output outside frozen roster")
    return hashes


def check_evaluation(audit: Audit, manifest: dict[str, Any], output_hashes: dict[str, str]) -> None:
    frozen = audit.get("evaluation/frozen_outputs.json")
    if frozen is not None and frozen != output_hashes:
        audit.fail("evaluation/frozen_outputs.json", "frozen output hashes/roster differ from current candidates")
    for sid, *_ in manifest["scenes"]:
        if any(not (audit.root / f"outputs/{sid}/{method}.json").exists() for method in manifest["methods"]):
            continue
        expected, names = pilot.evaluation_packet(sid, manifest)
        keys = audit.get(f"evaluation/keys/{sid}.json")
        if keys is not None and keys != names:
            audit.fail(sid, "evaluation key differs from frozen deterministic label assignment")
        for judge, model in enumerate(manifest["judge_models"]):
            payload = {**expected, "candidates": expected["candidates"] if judge == 0 else list(reversed(expected["candidates"]))}
            saved = audit.get(f"evaluation/packets/{sid}_{judge}.json")
            if saved is not None and saved != payload:
                audit.fail(f"evaluation/packets/{sid}_{judge}.json", "candidate/gold/source content or order differs from frozen inputs")
            result = audit.call(f"judgments/{sid}_{judge}", packet(pilot.JUDGE, payload, pilot.RATING_SCHEMA, model))
            if result is not None:
                audit.check(f"judgments/{sid}_{judge}", judgment_errors(result, list(names)))
    expected_calls = {f"{sid}_{j}.json" for sid, *_ in manifest["scenes"] for j, _ in enumerate(manifest["judge_models"])}
    for path in (audit.root / "calls/judgments").glob("*.json"):
        if path.name not in expected_calls:
            audit.fail(str(path.relative_to(audit.root)), "unexpected judgment outside frozen roster")


def run(stage: str, *, allow_missing: bool, review_resolutions: Path | None = None) -> dict[str, Any]:
    audit = Audit(root=ROOT, allow_missing=allow_missing)
    manifest = pilot.read(ROOT / "manifest.json")
    for path, expected in manifest["bindings"].items():
        actual = pilot.REPO / path
        if not actual.exists() or pilot.sha(actual) != expected:
            audit.fail(path, "frozen source binding mismatch")
    live = pilot.REPO / "src/translation/prompt_builder.py"
    snapshot = ROOT / "prompts/neutral_source.py"
    if pilot.sha(live) != pilot.sha(snapshot):
        audit.fail(str(live), "live neutral prompt differs from frozen snapshot")
    amendment = audit.get("validation_amendment.json")
    if amendment is not None:
        for rel, expected in amendment["bindings"].items():
            path = pilot.REPO / rel
            if not path.exists() or pilot.sha(path) != expected:
                audit.fail(rel, "validation amendment binding mismatch")
    output_hashes = check_generation(audit, manifest)
    if stage == "final":
        admission = audit.get("validation_admission.json")
        if admission is not None:
            if admission.get("output_hashes") != output_hashes:
                audit.fail("validation_admission.json", "candidate hashes changed after admission")
            if admission.get("manifest_sha256") != pilot.sha(ROOT / "manifest.json"):
                audit.fail("validation_admission.json", "source manifest changed after admission")
            if amendment is not None and admission.get("amendment_sha256") != pilot.sha(ROOT / "validation_amendment.json"):
                audit.fail("validation_admission.json", "validation amendment changed after admission")
        check_evaluation(audit, manifest, output_hashes)
    resolutions = {}
    if review_resolutions is not None:
        resolutions = pilot.read(review_resolutions)
    unresolved = [row for row in audit.warnings if not isinstance(resolutions.get(row["id"]), str) or not resolutions[row["id"]].strip()]
    if audit.failures:
        status = "fail"
    elif audit.missing:
        status = "incomplete"
    elif unresolved:
        status = "manual_review_required"
    else:
        status = "pass"
    result = {"schema": "style_pilot_validation.v1", "stage": stage, "status": status,
              "created_at": datetime.now(UTC).isoformat(), "allow_missing": allow_missing,
              "manifest_sha256": pilot.sha(ROOT / "manifest.json"), "validator_sha256": pilot.sha(Path(__file__)),
              "failures": audit.failures, "missing": sorted(set(audit.missing)), "warnings": audit.warnings,
              "diagnostics": audit.diagnostics,
              "unresolved_warnings": unresolved, "review_resolutions": resolutions,
              "read_file_hashes": audit.input_hashes, "output_hashes": output_hashes,
              "claim_limit": "Structural/provenance validation only; not semantic or style efficacy."}
    if stage == "pre-evaluation" and status == "pass":
        path = ROOT / "validation_admission.json"
        if path.exists():
            existing = pilot.read(path)
            if existing.get("output_hashes") != output_hashes or existing.get("manifest_sha256") != result["manifest_sha256"]:
                result["status"] = "fail"
                result["failures"].append({"path": str(path), "message": "existing admission binds different evidence"})
        elif any((ROOT / "calls/judgments").glob("*.json")) or any((ROOT / "requests/judgments").glob("*.json")):
            result["status"] = "fail"
            result["failures"].append({"path": "validation_admission.json", "message": "cannot create pre-judge admission after judgments started"})
        else:
            admission = {"schema": "style_pilot_validation_admission.v1", "created_at": result["created_at"],
                         "manifest_sha256": result["manifest_sha256"], "validator_sha256": result["validator_sha256"],
                         "amendment_sha256": pilot.sha(ROOT / "validation_amendment.json"),
                         "output_hashes": output_hashes, "generation_evidence_hashes": audit.input_hashes,
                         "review_resolutions": resolutions, "status": "admitted_for_exploratory_blind_judgment"}
            with path.open("x", encoding="utf-8") as handle:
                json.dump(admission, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only validation of frozen style pilot candidates and judgments.")
    parser.add_argument("stage", choices=["pre-evaluation", "final"])
    parser.add_argument("--allow-missing", action="store_true", help="Permit an incomplete progress check; never create admission while incomplete.")
    parser.add_argument("--review-resolutions", type=Path, help="JSON mapping warning IDs to source-backed manual review explanations.")
    args = parser.parse_args()
    result = run(args.stage, allow_missing=args.allow_missing, review_resolutions=args.review_resolutions)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = ROOT / f"validation/{args.stage}_{stamp}.json"
    pilot.write(path, result)
    print(json.dumps({k: result[k] for k in ("stage", "status", "failures", "missing", "unresolved_warnings")}, ensure_ascii=False, indent=2))
    print(f"Validation report: {path}")
    return 0 if result["status"] == "pass" or (args.allow_missing and result["status"] == "incomplete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
