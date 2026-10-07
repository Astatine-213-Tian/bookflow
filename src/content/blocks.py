"""Content and formatting comparison shared by source adapters and exporters."""

from __future__ import annotations

import copy
from difflib import SequenceMatcher


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


def content_signature(blocks: list[dict]) -> list[tuple]:
    """Compare editable presentation, excluding local archive bookkeeping."""
    # Markdown moves whitespace outside emphasis. Its styling has no visible
    # effect, while every character and non-whitespace style must be preserved.
    anchors = {b["anchor"]: i for i, b in enumerate(blocks) if b.get("anchor")}
    return [
        (
            b["kind"],
            b.get("level", 3) if b["kind"] == "heading" else None,
            b.get("alignment", "left"),
            b.get("language"),
            b.get("variant"),
            bool(b.get("footnote")),
            tuple(
                (
                    char,
                    tuple(sorted(r["styles"])) if not char.isspace() else (),
                    ("#block", anchors[r["href"][1:]])
                    if r.get("href", "").startswith("#") and r["href"][1:] in anchors
                    else r.get("href"),
                    r.get("link_role"),
                )
                for r in b["runs"]
                for char in r["text"]
            ),
        )
        for b in blocks
    ]


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
