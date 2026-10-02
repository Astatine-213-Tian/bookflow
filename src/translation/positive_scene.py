"""Direct positive-example translation with reviewed QA and text-preserving alignment.

Generated prose never passes through the older neutral/style editor. Alignment
returns indices only, so bilingual layout cannot rewrite Chinese sentences.
"""
from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from src.crawler.snapshot import load_chapter, load_manifest, write_json
from src.runtime.paths import repo_root
from src.translation.glossary import glossary_terms, matched_terms, normalize_lookup_key
from src.translation.sentence_translations import _find_occurrences, sentence_translation_entries
from src.translation.style_transfer import run_structured_attempt
from src.translation.style_transfer_assets import file_sha256, sha256_json

METHOD = "direct_scene_positive"
STRING = {"type": "string"}
INTS = {"type": "array", "items": {"type": "integer"}}


def object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


TEXT_SCHEMA = object_schema({"paragraphs": {"type": "array", "items": STRING},
                             "notes": {"type": "array", "items": STRING}})
QA_SCHEMA = object_schema({"issues": {"type": "array", "items": object_schema({
    "paragraph": {"type": "integer"}, "before": STRING, "after": STRING,
    "source_quote": STRING, "reason": STRING})}, "notes": {"type": "array", "items": STRING}})
ALIGN_SCHEMA = object_schema({"groups": {"type": "array", "items": object_schema({
    "english_indices": INTS, "chinese_indices": INTS})},
    "notes": {"type": "array", "items": STRING}})
QA_PROMPT = """Independently check every Chinese paragraph against the English scene.
Report ONLY demonstrable semantic errors, glossary violations or protected-quote changes.
Check omissions/additions, actors, agency, negation, degree, numbers, events, speaker and
causality. English is the authority. Do not polish style, expand concise idiomatic Chinese,
force English syntax, or treat natural paraphrases or pronouns as omissions. Glossary
aliases fix terminology when used as names/terms, not unrelated ordinary senses.
For each issue quote exact source evidence and one exact contiguous before fragment in
the numbered Chinese paragraph, with a minimal after repair. Do not invent author Chinese.
Zero issues is allowed. This is read-only review; proposed repairs need adjudication.
Return JSON only."""
ALIGN_PROMPT = """Align English and already-final Chinese paragraphs for a bilingual EPUB.
Return indices ONLY. Never write or revise Chinese text. Choose the SMALLEST contiguous
groups that cover equivalent meaning; usually one English paragraph to one Chinese,
but use many-to-many groups when the translation naturally combined/split/reordered local
clauses. Preserve the order of BOTH streams. Every index from both streams must occur
exactly once in order. Every group must have at least one paragraph from each language.
Do not force one-to-one correspondence, split Chinese sentences or combine the whole
scene unnecessarily. Put any semantic mismatch in notes. Return JSON only."""


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_digest(chapter: dict[str, Any]) -> str:
    return sha256_json({key: chapter.get(key) for key in ("title", "paragraphs", "blocks")})


def prompt_glossary(glossary: dict[str, Any], text: str) -> dict[str, str]:
    """JSON loses GlossaryTermMap's alias lookup; expose relevant aliases explicitly."""
    terms = dict(glossary_terms(glossary))
    for canonical, entry in glossary.get("terms", {}).items():
        if isinstance(entry, dict) and entry.get("zh"):
            for alias in entry.get("aliases", []):
                if (normalize_lookup_key(alias) != normalize_lookup_key(canonical)
                        and matched_terms(text, {alias: entry["zh"]})):
                    terms[alias] = entry["zh"]
    return terms


def scene_windows(chapter: dict[str, Any], target_words: int) -> list[list[dict[str, Any]]]:
    """Keep source separators, complete paragraphs and short scene tails intact."""
    by_index = {int(x["index"]): x for x in chapter["paragraphs"]}
    sections: list[list[dict[str, Any]]] = [[]]
    for block in chapter.get("blocks") or [{"type": "content", "index": i} for i in by_index]:
        if block["type"] == "content":
            sections[-1].append(by_index[int(block["index"])])
        elif sections[-1]:
            sections.append([])
    result = []
    for section in sections:
        windows: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        count = 0
        for row in section:
            current.append(row)
            count += len(row["english"].split())
            if count >= target_words:
                windows.append(current)
                current, count = [], 0
        if current:
            if count < 120 and windows:
                windows[-1].extend(current)
            else:
                windows.append(current)
        result.extend(windows)
    return result


def alignment_errors(request: dict[str, Any], result: dict[str, Any]) -> list[str]:
    groups = result.get("groups") or []
    if not groups or any(not g.get("english_indices") or not g.get("chinese_indices") for g in groups):
        return ["Every alignment group must contain both languages"]
    expected = {"english_indices": [r["index"] for r in request["english"]],
                "chinese_indices": list(range(len(request["chinese"]))) }
    return [f"Incomplete, duplicated or reordered {key}"
            for key, values in expected.items() if [i for g in groups for i in g[key]] != values]


def text_errors(request: dict[str, Any], result: dict[str, Any]) -> list[str]:
    rows = result.get("paragraphs")
    return [] if isinstance(rows, list) and rows and all(isinstance(x, str) and x.strip() for x in rows) else ["Empty Chinese scene"]


def invoke(run: Path, name: str, prompt: str, payload: dict[str, Any], schema: dict[str, Any],
           settings: dict[str, Any], *, review: bool = False, validator=None) -> dict[str, Any]:
    packet = {"prompt": prompt, "payload": payload, "schema": schema,
              "model": settings["review_model" if review else "model"],
              "reasoning_effort": settings["reasoning_effort"]}
    request_path = run / "requests" / f"{name}.json"
    output = run / "calls" / f"{name}.json"
    binding_path = run / "calls" / f"{name}.binding.json"
    digest = sha256_json(packet)
    if output.exists():
        binding = read(binding_path)
        if binding != {"input_sha256": digest, "output_sha256": file_sha256(output)}:
            raise ValueError(f"Resume binding mismatch: {name}")
        return read(output)["result"]
    write_json(request_path, packet)
    schema_path = run / "schemas" / f"{name.split('/')[0]}.json"
    # Same schema across workers; the parent writes these before launching jobs.
    if read(schema_path) != schema:
        raise ValueError("Schema drift")
    for attempt in (1, 2):
        record = run_structured_attempt(request=payload, prompt_template=prompt,
            schema_path=schema_path, output_path=output, model=packet["model"],
            reasoning_effort=packet["reasoning_effort"], timeout_seconds=settings["timeout_seconds"],
            codex_bin="codex", attempt=attempt, result_validator=validator or (lambda req, res: []))
        write_json(run / "attempts" / f"{name}.{attempt}.json", record)
        if record["status"] == "success":
            write_json(binding_path, {"input_sha256": digest, "output_sha256": file_sha256(output)})
            print(f"complete {name}", flush=True)
            return read(output)["result"]
    raise RuntimeError(f"Failed {name}: {record['validation_errors']}")


def resolve_issues(draft: dict[str, Any], qa: dict[str, Any], resolution: dict[str, Any]) -> list[str]:
    if resolution.get("qa_sha256") != sha256_json(qa):
        raise ValueError("QA adjudication is stale")
    decisions = resolution.get("decisions", [])
    if [d["issue"] for d in decisions] != list(range(len(qa["issues"]))):
        raise ValueError("Every QA issue needs an explicit adjudication")
    paragraphs = list(draft["paragraphs"])
    for decision, issue in zip(decisions, qa["issues"]):
        if not decision.get("reason") or not isinstance(decision.get("apply"), bool):
            raise ValueError("Adjudication needs boolean apply and a reason")
        if decision["apply"]:
            index, before = issue["paragraph"], issue["before"]
            if not before or paragraphs[index].count(before) != 1:
                raise ValueError("QA repair must be exact and unique")
            paragraphs[index] = paragraphs[index].replace(before, decision.get("after", issue["after"]), 1)
    if not all(x.strip() for x in paragraphs):
        raise ValueError("QA repair erased a paragraph")
    return paragraphs


def run_positive_scenes(*, snapshot_dir: Path, run_dir: Path, config: dict[str, Any],
                        baseline_snapshot: Path, baseline_run: Path) -> dict[str, Any]:
    run = run_dir.resolve()
    settings = config["scene_positive"]
    runtime = run / "runtime"
    inputs = {"config.json": config, "glossary.json": read(repo_root() / config["glossary_path"])}
    for filename, data in inputs.items():
        path = runtime / filename
        if path.exists() and read(path) != data:
            raise ValueError(f"Frozen runtime changed: {filename}; use a fresh run")
        write_json(path, data)
    for key, name in (("asset", "asset.json"), ("prompt", "prompt.md")):
        path = repo_root() / settings[f"{key}_path"]
        if file_sha256(path) != settings[f"{key}_file_sha256"]:
            raise ValueError(f"Configured {key} hash mismatch")
        shutil.copyfile(path, runtime / name)
    for name, schema in (("generate", TEXT_SCHEMA), ("review", QA_SCHEMA), ("align", ALIGN_SCHEMA)):
        write_json(run / "schemas" / f"{name}.json", schema)
    manifest, old_manifest = load_manifest(snapshot_dir), load_manifest(baseline_snapshot)
    old = {x["source_id"]: x for x in old_manifest["chapters"]}
    asset, glossary = read(runtime / "asset.json"), inputs["glossary.json"]
    requests, reused, sources = [], [], {}
    for item in manifest["chapters"]:
        cid = str(item["id"])
        chapter = load_chapter(snapshot_dir, manifest, cid)
        sources[cid] = source_digest(chapter)
        previous = old.get(item["source_id"])
        if previous:
            old_chapter = load_chapter(baseline_snapshot, old_manifest, str(previous["id"]))
            same = source_digest(chapter) == source_digest(old_chapter)
            equivalence = run / "reuse_reviews" / f"{cid}.json"
            evidence: dict[str, Any] = {}
            if not same and equivalence.exists():
                evidence = read(equivalence)
                same = (evidence.get("source_sha256") == sources[cid]
                        and evidence.get("baseline_sha256") == source_digest(old_chapter)
                        and bool(evidence.get("reason")))
            if same:
                source = baseline_run / "translations" / f"{previous['id']}.json"
                destination = run / "translations" / f"{cid}.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                if evidence.get("translation_replacements"):
                    reused_data = read(destination)
                    by_index = {row["index"]: row for row in reused_data["translations"]}
                    for replacement in evidence["translation_replacements"]:
                        row = by_index[replacement["index"]]
                        if not replacement["before"] or row["zh"].count(replacement["before"]) != 1:
                            raise ValueError("Reuse correction is not exact and unique")
                        row["zh"] = row["zh"].replace(replacement["before"], replacement["after"], 1)
                    write_json(destination, reused_data)
                reused.append({"chapter_id": cid, "path": str(source.resolve()), "sha256": file_sha256(source)})
                continue
        rows = chapter["paragraphs"]
        for number, window in enumerate(scene_windows(chapter, settings["target_words"]), 1):
            sid = f"{cid}_{number:03d}"
            first, last = window[0]["index"], window[-1]["index"]
            context = settings["context_paragraphs"]
            context_rows = rows[max(0, first-context):last+1+context]
            payload = {"sample_id": sid, "book": config["title"], "chapter_title": chapter["title"],
                "english": window, "context_before_do_not_translate": rows[max(0, first-context):first],
                "context_after_do_not_translate": rows[last+1:last+1+context],
                "authentic_examples": asset["authentic_examples"], "wording_examples": asset["wording_examples"],
                "glossary": prompt_glossary(glossary, " ".join(x["english"] for x in context_rows)),
                "sentence_translations": glossary.get("sentence_translations", [])}
            requests.append({"scene_id": sid, "chapter_id": cid, "payload": payload})
    run_manifest = {"schema": METHOD, "snapshot_dir": str(snapshot_dir.resolve()),
                    "source_bindings": sources, "reused": reused,
                    "scenes": [{"scene_id": x["scene_id"], "chapter_id": x["chapter_id"],
                                "indices": [r["index"] for r in x["payload"]["english"]]} for x in requests]}
    manifest_path = run / "run_manifest.json"
    if manifest_path.exists() and read(manifest_path) != run_manifest:
        raise ValueError("Scene inputs/reuse baseline changed")
    write_json(manifest_path, run_manifest)

    def process(scene: dict[str, Any]) -> dict[str, Any]:
        sid, payload = scene["scene_id"], scene["payload"]
        draft = invoke(run, f"generate/{sid}", (runtime / "prompt.md").read_text(), payload,
                       TEXT_SCHEMA, settings, validator=text_errors)
        audit_payload = {k: v for k, v in payload.items() if k not in ("authentic_examples", "wording_examples")}
        audit_payload["chinese"] = [{"index": i, "zh": x} for i, x in enumerate(draft["paragraphs"])]
        qa = invoke(run, f"review/{sid}", QA_PROMPT, audit_payload, QA_SCHEMA, settings, review=True)
        paragraphs = draft["paragraphs"]
        if qa["issues"]:
            resolution = run / "resolutions" / f"{sid}.json"
            if not resolution.exists():
                return {"scene_id": sid, "pending_issues": len(qa["issues"])}
            paragraphs = resolve_issues(draft, qa, read(resolution))
        manual_path = run / "manual_reviews" / f"{sid}.json"
        if manual_path.exists():
            manual = read(manual_path)
            if manual["draft_sha256"] != sha256_json(paragraphs):
                raise ValueError("Independent manual review is stale")
            paragraphs = resolve_issues({"paragraphs": paragraphs}, manual["review"], manual["resolution"])
        alignment_payload = {"english": payload["english"], "chinese": paragraphs}
        alignment_name = f"align/{sid}"
        prior_alignment = run / "requests" / f"{alignment_name}.json"
        if prior_alignment.exists() and read(prior_alignment)["payload"] != alignment_payload:
            alignment_name += "." + sha256_json(alignment_payload)[:12]
        alignment = invoke(run, alignment_name, ALIGN_PROMPT, alignment_payload, ALIGN_SCHEMA,
                           settings, review=True, validator=alignment_errors)
        result = {"scene_id": sid, "paragraphs": paragraphs, "alignment": alignment}
        write_json(run / "scenes" / f"{sid}.json", result)
        return {"scene_id": sid, "pending_issues": 0}

    with ThreadPoolExecutor(max_workers=settings.get("workers", 2)) as pool:
        results = list(pool.map(process, requests))
    pending = [x for x in results if x["pending_issues"]]
    write_json(run / "status.json", {"pending": pending, "scenes": len(requests), "reused": len(reused)})
    if pending:
        raise ValueError(f"Source review requires adjudication: {pending}")
    for cid in {x["chapter_id"] for x in requests}:
        groups = []
        for scene in (x for x in requests if x["chapter_id"] == cid):
            data = read(run / "scenes" / f"{scene['scene_id']}.json")
            groups.extend({"english_indices": g["english_indices"],
                "paragraphs": [data["paragraphs"][i] for i in g["chinese_indices"]]}
                for g in data["alignment"]["groups"])
        write_json(run / "translations" / f"{cid}.json", {"chapter_id": cid, "groups": groups})
    paths = [p for folder in ("runtime", "schemas", "requests", "calls", "resolutions", "manual_reviews", "scenes", "translations", "reuse_reviews")
             for p in (run / folder).rglob("*") if p.is_file()]
    paths.append(manifest_path)
    write_json(run / "provenance.json", {str(p.relative_to(run)): file_sha256(p) for p in paths})
    return validate_positive_run(run, config=config)


def is_positive_run(run: Path) -> bool:
    path = run / "run_manifest.json"
    return path.exists() and read(path).get("schema") == METHOD


def validate_positive_run(run: Path, *, config: dict[str, Any] | None = None,
                          snapshot_dir: Path | None = None) -> dict[str, Any]:
    bindings = read(run / "provenance.json")
    for path, digest in bindings.items():
        if file_sha256(run / path) != digest:
            raise ValueError(f"Positive-run artifact changed after review: {path}")
    manifest = read(run / "run_manifest.json")
    if config and read(run / "runtime/glossary.json") != read(repo_root() / config["glossary_path"]):
        raise ValueError("Glossary changed after scene review")
    snapshot = snapshot_dir or Path(manifest["snapshot_dir"])
    source_manifest = load_manifest(snapshot)
    protected = sentence_translation_entries(read(run / "runtime/glossary.json"))
    protected_count = 0
    if set(manifest["source_bindings"]) != {str(x["id"]) for x in source_manifest["chapters"]}:
        raise ValueError("Chapter coverage changed")
    for cid, digest in manifest["source_bindings"].items():
        chapter = load_chapter(snapshot, source_manifest, cid)
        if source_digest(chapter) != digest:
            raise ValueError(f"Reviewed English changed: {cid}")
        translated = read(run / "translations" / f"{cid}.json")
        if "groups" in translated:
            groups = translated["groups"]
            indices = [i for g in translated["groups"] for i in g["english_indices"]]
            texts = [p for g in translated["groups"] for p in g["paragraphs"]]
        else:
            groups = [{"english_indices": [x["index"]], "paragraphs": [x["zh"]]}
                      for x in translated["translations"]]
            indices = [x["index"] for x in translated["translations"]]
            texts = [x["zh"] for x in translated["translations"]]
        if indices != [p["index"] for p in chapter["paragraphs"]] or not all(x.strip() for x in texts):
            raise ValueError(f"Incomplete bilingual coverage: {cid}")
        for entry in protected:
            for occurrence in _find_occurrences(chapter["paragraphs"], entry):
                zh = "\n".join(p for g in groups if set(g["english_indices"]) & set(occurrence["indexes"])
                               for p in g["paragraphs"])
                if not all(line in zh for line in entry.zh):
                    raise ValueError(f"Protected quotation changed in {cid}: {occurrence['indexes']}")
                protected_count += 1
    return {"method": METHOD, "chunks": manifest["scenes"], "reused_chapters": len(manifest["reused"]),
            "protected_quotation_occurrences": protected_count}
