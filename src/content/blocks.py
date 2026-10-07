"""Content and formatting comparison shared by source adapters and exporters."""

from __future__ import annotations

import copy
from difflib import SequenceMatcher

from notion_books import content_signature


def block_text(block: dict) -> str:
    return "".join(run["text"] for run in block.get("runs", []))


def has_reference_identity(block: dict) -> bool:
    return bool(
        block.get("anchor")
        or block.get("footnote")
        or any(run.get("link_role") for run in block.get("runs", []))
    )


def removable_empty_paragraph(block: dict) -> bool:
    return (
        block["kind"] == "paragraph"
        and not block_text(block).strip()
        and not block.get("variant")
        and not has_reference_identity(block)
    )


def replace_run_text(runs: list[dict], text: str) -> list[dict]:
    """Apply textual edits while retaining styles on surviving characters."""
    before = "".join(run["text"] for run in runs)
    annotations = [
        {k: v for k, v in run.items() if k != "text"}
        for run in runs
        for _ in run["text"]
    ]
    result: list[dict] = []
    for kind, a, b, c, d in SequenceMatcher(
        None, before, text, autojunk=False
    ).get_opcodes():
        for offset, char in enumerate(text[c:d]):
            source = a + offset if kind == "equal" else min(a + offset, max(a, b - 1))
            active = (
                annotations[min(source, len(annotations) - 1)]
                if annotations
                else {"styles": []}
            )
            if (
                result
                and {k: v for k, v in result[-1].items() if k != "text"} == active
            ):
                result[-1]["text"] += char
            else:
                result.append({"text": char, **copy.deepcopy(active)})
    return result
