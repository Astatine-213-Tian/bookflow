"""Normalize structured content without rendering an archive or contacting a service."""

from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from pathlib import Path

from src.content.normalization import (
    AUTHOR_NOTE_HEADING_RE,
    AUTHOR_NOTE_PARAGRAPH_RE,
    DECORATIVE_END_MARKER_RE,
    NormalizationReport,
    _normalize_plain_text,
    scan_content_issues,
)

RULES_SHA256 = "913dec50abe5803e3ca953969598fe3a9b2ae4976569e75361a68b7292c4c031"


def normalize_text(
    text: str,
    *,
    title: bool = False,
    member: str = "text",
    report: NormalizationReport | None = None,
) -> str:
    return _normalize_plain_text(
        text.replace("\u2028", "\n").replace("\u2029", "\n"),
        preserve_ordinals=title,
        remove_han_spaces=not title,
        title_punctuation=title,
        end_marker=not title,
        force_fanwai_title=False,
        member=member,
        report=report or NormalizationReport(path=Path("content"), applied=True),
    )


def _replace_runs(runs: list[dict], text: str) -> list[dict]:
    """Apply textual edits while retaining styles on surviving characters."""
    before = "".join(run["text"] for run in runs)
    styles = [run.get("styles", []) for run in runs for _ in run["text"]]
    result: list[dict] = []
    for kind, a, b, c, d in SequenceMatcher(
        None, before, text, autojunk=False
    ).get_opcodes():
        for offset, char in enumerate(text[c:d]):
            source = a + offset if kind == "equal" else min(a + offset, max(a, b - 1))
            active = styles[min(source, len(styles) - 1)] if styles else []
            if result and result[-1]["styles"] == active:
                result[-1]["text"] += char
            else:
                result.append({"text": char, "styles": list(active)})
    return result


def normalize_chapter(
    chapter: dict, *, member: str = "chapter", report: NormalizationReport | None = None
) -> dict:
    report = report or NormalizationReport(path=Path("content"), applied=True)
    result = copy.deepcopy(chapter)
    result["title"] = normalize_text(
        result["title"], title=True, member=member, report=report
    )
    blocks = []
    for block in result["blocks"]:
        if block.get("variant") == "original":
            blocks.append(block)
            continue
        text = "".join(run["text"] for run in block["runs"])
        normalized = normalize_text(
            text, title=block["kind"] == "heading", member=member, report=report
        )
        normalized = normalized.lstrip(" \t\u3000")
        block["runs"] = _replace_runs(block["runs"], normalized)
        if block["kind"] == "heading" or (
            block["kind"] == "paragraph"
            and block.get("alignment") == "center"
            and block["runs"]
            and all("bold" in r["styles"] for r in block["runs"])
        ):
            block.update(kind="heading", level=3)
        if block["kind"] == "paragraph":
            if re.fullmatch(r"(?:\*\s*){3,}", normalized.strip()):
                block["runs"] = _replace_runs(block["runs"], "***")
                block["alignment"] = "center"
            elif DECORATIVE_END_MARKER_RE.fullmatch(normalized.strip()):
                block["alignment"] = "center"
        blocks.append(block)
    # Structural rules operate on block content, regardless of the source format.
    expanded = []
    for block in blocks:
        text = "".join(r["text"] for r in block["runs"])
        match = (
            AUTHOR_NOTE_HEADING_RE.search(text)
            if block["kind"] == "paragraph" and not block.get("variant")
            else None
        )
        if match and text[: match.start()].strip():
            offset = match.start()
            left, right = copy.deepcopy(block), copy.deepcopy(block)
            left["runs"], right["runs"] = [], []
            cursor = 0
            for run in block["runs"]:
                cut = max(0, min(len(run["text"]), offset - cursor))
                if cut:
                    left["runs"].append({**run, "text": run["text"][:cut]})
                if cut < len(run["text"]):
                    right["runs"].append({**run, "text": run["text"][cut:]})
                cursor += len(run["text"])
            expanded.extend([left, right])
            report.record_change(
                "author_note_paragraph_break_inserted",
                member,
                1,
                text,
                "\n".join([text[:offset], text[offset:]]),
            )
        else:
            expanded.append(block)
    blocks = []
    for block in expanded:
        text = "".join(r["text"] for r in block["runs"])
        previous = blocks[-1] if blocks else {}
        before = "".join(r["text"] for r in previous.get("runs", []))
        if (
            previous.get("kind") == block["kind"] == "paragraph"
            and not previous.get("variant")
            and not block.get("variant")
            and previous.get("language") == block.get("language")
            and previous.get("alignment", "left") == block.get("alignment", "left")
            and (
                text.strip() in {"”", "’"}
                or before.rstrip().endswith(("，", ","))
                and text.strip()
                and not AUTHOR_NOTE_PARAGRAPH_RE.match(text)
                and not re.fullmatch(r"(?:\*\s*){3,}", text.strip())
            )
        ):
            previous["runs"].extend(block["runs"])
            report.record_change(
                "paragraph_break_merged", member, 1, before + "\n" + text, before + text
            )
        else:
            blocks.append(block)
    while (
        blocks
        and blocks[0]["kind"] == "paragraph"
        and not "".join(r["text"] for r in blocks[0]["runs"]).strip()
    ):
        blocks.pop(0)
        report.record_change(
            "chapter_leading_empty_removed", member, 1, "empty paragraph", ""
        )
    if result.get("role") != "intro":
        scan_content_issues(
            member,
            [
                "".join(r["text"] for r in b["runs"])
                for b in blocks
                if b["kind"] in {"paragraph", "quote"}
                and b.get("variant") != "original"
            ],
            [result["title"]],
            report,
        )
    result["blocks"] = blocks
    return result


def normalize_book(source: dict) -> tuple[dict, dict]:
    book = copy.deepcopy(source)
    report = NormalizationReport(path=Path("content"), applied=True)
    book["chapters"] = {
        key: normalize_chapter(ch, member=key, report=report)
        for key, ch in book["chapters"].items()
    }
    book["extras"] = [
        normalize_chapter(ch, member=f"extra:{index}", report=report)
        for index, ch in enumerate(book.get("extras", []))
    ]
    for key in ("title", "description"):
        if book["metadata"].get(key):
            book["metadata"][key] = normalize_text(
                book["metadata"][key], title=key == "title", report=report
            )

    def headings(nodes: list[dict]) -> None:
        for node in nodes:
            if "children" in node:
                node["title"] = normalize_text(node["title"], title=True, report=report)
                headings(node["children"])

    headings(book["sections"])
    return book, report.to_dict()
