"""Apply reviewed changes locally, keeping inputs and resumable reports intact."""

from __future__ import annotations

import json
from pathlib import Path

from src.content.changes import apply_changes, content_hash
from src.content.prepared import load_prepared_source
from src.runtime.files import write_json
from src.workflows.ingest import OutputOptions, write_book
from src.workflows.prepare import preparation_fingerprint, save_prepared


def update_book(
    source: Path,
    change_path: Path,
    run_dir: Path,
    *,
    outputs: OutputOptions | None = None,
) -> Path:
    candidate = run_dir / "source.json"
    if source.resolve() == candidate.resolve():
        raise ValueError("Use a fresh run directory; input is preserved")
    current, cover, mime = load_prepared_source(source)
    change = json.loads(change_path.read_text())
    signature = {
        "source": content_hash(current),
        "change": content_hash(change),
        "rules": preparation_fingerprint(),
    }
    stamp = run_dir / "change.json"
    if stamp.exists():
        if json.loads(stamp.read_text()) != signature:
            raise ValueError("Update inputs changed; use a fresh run directory")
    elif candidate.exists():
        raise ValueError("Update destination contains unrelated source.json")
    if candidate.exists():
        result, cover, mime = load_prepared_source(candidate)
    else:
        result, report = apply_changes(current, change)
        write_json(stamp, signature)
        save_prepared(result, run_dir, {"normalization": report}, cover, mime)
    if outputs is not None:
        write_book(result, outputs, cover=cover, cover_mime=mime, input_path=source)
    return candidate
