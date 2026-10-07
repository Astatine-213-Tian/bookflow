"""Shared read-only Codex CLI transport; callers own prompts and decision validation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def extract_review_payload(output: str) -> dict[str, Any]:
    stripped = output.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object found in Codex review output")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Codex review output must be a JSON object")
    return payload


def run_review_prompt(prompt: str, timeout_seconds: int) -> str:
    codex_bin = os.environ.get("BOOKLIB_CODEX_BIN", "codex")
    if shutil.which(codex_bin) is None:
        raise RuntimeError(f"Codex executable not found: {codex_bin}")
    with tempfile.TemporaryDirectory(prefix="book-normalize-codex-review-") as temp:
        output_path = Path(temp) / "review.json"
        command = [
            codex_bin,
            "exec",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_path),
            "-C",
            str(Path(__file__).resolve().parents[2]),
            "-",
        ]
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            detail = (result.stdout or "Codex review failed")[:500]
            raise RuntimeError(
                f"Codex review exited with {result.returncode}: {detail}"
            )
        if not output_path.exists():
            raise RuntimeError("Codex review did not produce an output message")
        return output_path.read_text(encoding="utf-8")
