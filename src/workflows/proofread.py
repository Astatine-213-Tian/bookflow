"""Collect reference evidence, review suspect text and apply bounded corrections."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.content.contract import validate_book
from src.content.prepared import load_prepared_source, save_source
from src.content.proofread import (
    apply_plan,
    completion_candidates,
    completion_prompt,
    note_review_prompt,
    plan_proofread,
    review_prompt,
    reviewed_completions,
    reviewed_notes,
    reviewed_operations,
    summary,
)
from src.content.quote_review import review_fingerprint
from src.crawler.providers.jjwxc.reference import collect_reference, reference_url
from src.runtime.codex_review import extract_review_payload, run_review_prompt
from src.runtime.files import write_json


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def prepare_proofread(
    run_dir: Path,
    *,
    notion: str | None = None,
    input_path: Path | None = None,
    jinjiang: str | None = None,
    config_path: Path,
    flagged: Path | None = None,
) -> dict:
    if bool(notion) == bool(input_path):
        raise ValueError(
            "Choose exactly one existing Notion work or local EPUB/source JSON"
        )
    request = {
        "notion": notion,
        "input": str(input_path.resolve()) if input_path else None,
        "jinjiang": jinjiang,
        "config": str(config_path.resolve()),
        "flagged_sha256": review_fingerprint(load(flagged)) if flagged else None,
    }
    request_path = run_dir / "request.json"
    if request_path.exists() and load(request_path) != request:
        raise ValueError(
            "Run directory belongs to different inputs; choose a fresh directory"
        )
    write_json(request_path, request)
    original_dir = run_dir / "original"
    cover, cover_mime = None, "image/jpeg"
    if (original_dir / "source.json").exists():
        original, cover, cover_mime = load_prepared_source(original_dir / "source.json")
    elif notion:
        from src.notion.api import api_token
        from src.notion.mcp import AUTH_FILE, TokenStore, connect
        from src.notion.proofread import snapshot_book

        api_token()

        async def capture():
            store = TokenStore(AUTH_FILE)
            with store.locked():
                async with connect(store) as tools:
                    return await snapshot_book(
                        notion, load(config_path), original_dir, tools=tools
                    )

        original, _ = asyncio.run(capture())
    else:
        if input_path.suffix.lower() == ".epub":
            from src.inputs.epub import read_epub_source

            imported = read_epub_source(input_path)
            original, cover, cover_mime = (
                imported.source,
                imported.cover,
                imported.cover_mime,
            )
        else:
            original, cover, cover_mime = load_prepared_source(input_path)
        save_source(original, original_dir / "source.json", cover, cover_mime)
    value = jinjiang or original["metadata"].get("source", "")
    reference_url(value)
    reference_path = collect_reference(value, run_dir / "reference")
    reference = load(reference_path)
    plan = plan_proofread(
        original,
        reference,
        flagged=load(flagged) if flagged else None,
        reference_evidence=load(run_dir / "reference/evidence.json"),
    )
    old = run_dir / "plan.json"
    if old.exists() and load(old)["fingerprint"] != plan["fingerprint"]:
        raise ValueError(
            "Evidence changed; choose a fresh run so saved decisions/journals remain recoverable"
        )
    write_json(old, plan)
    candidate, _ = apply_plan(original, reference, plan)
    validate_book(candidate)
    save_source(candidate, run_dir / "candidate.json", cover, cover_mime)
    report = summary(plan)
    report["reference_coverage"] = {
        k: load(run_dir / "reference/evidence.json")[k] for k in ("readable", "total")
    }
    write_json(run_dir / "report.json", report)
    return report


def review_proofread(run_dir: Path, *, runner=None) -> dict:
    plan = load(run_dir / "plan.json")
    decisions_path = run_dir / "decisions.json"
    if decisions_path.exists():
        decisions = load(decisions_path)
        reviewed_operations(plan, decisions)
        rows = decisions["reviews"]
    else:
        rows = []
    run = runner or (lambda prompt: run_review_prompt(prompt, 300))
    for start in range(len(rows), len(plan["findings"]), 6):
        findings = plan["findings"][start : start + 6]
        batch_path = run_dir / "reviews" / f"{start:04d}.json"
        if batch_path.exists():
            batch = load(batch_path)
        else:
            response = extract_review_payload(run(review_prompt(findings)))
            if set(response) != {"reviews"}:
                raise ValueError("Review response has unexpected fields")
            batch = {"fingerprint": plan["fingerprint"], "reviews": response["reviews"]}
        reviewed_operations({**plan, "findings": findings}, batch)
        write_json(batch_path, batch)
        rows.extend(batch["reviews"])
        print(
            f"Text review: {min(start + 6, len(plan['findings']))}/{len(plan['findings'])}",
            flush=True,
        )
    decisions = {"fingerprint": plan["fingerprint"], "reviews": rows}
    reviewed_operations(plan, decisions)
    write_json(decisions_path, decisions)
    notes = [n for n in plan.get("notes", []) if n["status"] == "note_cleanup_review"]
    notes_path = run_dir / "note-decisions.json"
    if notes_path.exists():
        note_decisions = load(notes_path)
    elif notes:
        response = extract_review_payload(run(note_review_prompt(notes)))
        if set(response) != {"reviews"}:
            raise ValueError("Author-note review response has unexpected fields")
        note_decisions = {
            "fingerprint": plan["fingerprint"],
            "reviews": response["reviews"],
        }
    else:
        note_decisions = {"fingerprint": plan["fingerprint"], "reviews": []}
    reviewed_notes(plan, note_decisions)
    write_json(notes_path, note_decisions)
    completions = completion_candidates(plan)
    completion_path = run_dir / "completion-decisions.json"
    if completion_path.exists():
        completion_decisions = load(completion_path)
    elif completions:
        response = extract_review_payload(run(completion_prompt(completions)))
        if set(response) != {"reviews"}:
            raise ValueError("Note-completion review response has unexpected fields")
        completion_decisions = {
            "fingerprint": plan["fingerprint"],
            "reviews": response["reviews"],
        }
    else:
        completion_decisions = {"fingerprint": plan["fingerprint"], "reviews": []}
    reviewed_completions(plan, completion_decisions)
    write_json(completion_path, completion_decisions)
    return decisions


def apply_proofread(
    run_dir: Path, *, state_root: Path = Path("state/notion/proofread")
) -> dict:
    original, cover, cover_mime = load_prepared_source(run_dir / "original/source.json")
    reference = load(run_dir / "reference/source.json")
    plan = load(run_dir / "plan.json")
    decisions_path = run_dir / "decisions.json"
    decisions = load(decisions_path) if decisions_path.exists() else None
    notes_path = run_dir / "note-decisions.json"
    note_decisions = load(notes_path) if notes_path.exists() else None
    completion_path = run_dir / "completion-decisions.json"
    completion_decisions = load(completion_path) if completion_path.exists() else None
    candidate, operations = apply_plan(
        original, reference, plan, decisions, note_decisions, completion_decisions
    )
    validate_book(candidate)
    save_source(candidate, run_dir / "candidate.json", cover, cover_mime)
    evidence_path = run_dir / "original/evidence.json"
    if not evidence_path.exists():
        report = {
            "output": str(run_dir / "candidate.json"),
            "operations": len(operations),
            "verified": True,
        }
    else:
        from src.notion.api import api_token
        from src.notion.mcp import AUTH_FILE, TokenStore, connect, exclusive_lock
        from src.notion.proofread import apply_edits

        api_token()
        evidence = load(evidence_path)
        state_dir = state_root / evidence["work_id"] / plan["fingerprint"][:16]
        journal_path = state_dir / "journal.json"
        # Retain the exact request and recovery inputs independently of working outputs.
        recovery = {
            "original": original,
            "reference": reference,
            "plan": plan,
            "decisions": decisions,
            "note_decisions": note_decisions,
            "evidence": evidence,
            "operations": operations,
        }
        if completion_decisions is not None:
            recovery["completion_decisions"] = completion_decisions
        recovery_path = state_dir / "recovery.json"
        if recovery_path.exists() and load(recovery_path) != recovery:
            raise ValueError(
                "Saved recovery request differs; retain the original decisions"
            )
        write_json(recovery_path, recovery)

        async def write():
            with exclusive_lock(state_dir.parent / "proofread.lock"):
                store = TokenStore(AUTH_FILE)
                with store.locked():
                    async with connect(store) as tools:
                        return await apply_edits(
                            original,
                            candidate,
                            evidence,
                            operations,
                            journal_path,
                            tools=tools,
                        )

        report = asyncio.run(write())
    report["text_repairs"] = sum("review_id" in op for op in operations)
    report["author_note_paragraphs_normalized"] = sum(
        op.get("reason") == "author_note_normalization" for op in operations
    )
    report["author_notes_added"] = sum(op["kind"] == "append_note" for op in operations)
    report["author_note_dividers_added"] = sum(
        op["kind"] == "insert_divider" for op in operations
    )
    report["author_notes_completed"] = len(
        {op["note_review_id"] for op in operations if op["kind"] == "insert_note"}
    )
    report["unreviewed_suspects"] = len(plan["findings"]) if decisions is None else 0
    report["unresolved_gaps"] = sum(g["status"] != "matched" for g in plan["gaps"])
    write_json(run_dir / "result.json", report)
    return report
