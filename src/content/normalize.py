"""Normalize structured content without rendering an archive or contacting a service."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from src.content.blocks import (
    block_text,
    has_reference_identity,
    removable_empty_paragraph,
    replace_run_text,
)
from src.content.normalization import (
    AUTHOR_NOTE_HEADING_RE,
    AUTHOR_NOTE_PARAGRAPH_RE,
    DECORATIVE_END_MARKER_RE,
    NormalizationReport,
    _normalize_plain_text,
    normalize_alphanumeric_width,
    scan_content_issues,
)
from src.content.numerals import format_chinese_numeral
from src.content.titles import normalize_outline, normalize_volume_colors

RULES_SHA256 = "cbe71c1915ed98bd86dae2885cc55dd5e0c9d41a0768f34fa1c3a512660d4a55"

SECTION_NUMBER = r"(?:[0-9０-９]{1,3}|[一二三四五六七八九十百零〇]+)"
SECTION_LABEL_RE = re.compile(
    rf"(?:[（(](?P<wrapped>{SECTION_NUMBER})[）)]|(?P<bare>{SECTION_NUMBER})[、.]?)"
)
NUMBERED_HEADING_RE = re.compile(
    rf"(?:[（(]{SECTION_NUMBER}[）)]|{SECTION_NUMBER}(?:、|\.(?![0-9０-９]))"
    rf"|第{SECTION_NUMBER}[章回节])"
)
LIST_MARKER_RE = re.compile(
    r"^\s*([0-9０-９]{1,3})[,，、.．][ \t\u3000]*(?=[^\d\s.,，．])"
)


def normalize_list_markers(
    blocks: list[dict],
    *,
    member: str = "chapter",
    report: NormalizationReport | None = None,
) -> list[dict]:
    """Keep numbered prose as paragraphs, with consistent `1. ` prefixes."""
    result = copy.deepcopy(blocks)
    candidates = []
    for block in result:
        text = block_text(block)
        if (
            block["kind"] == "paragraph"
            and not block.get("variant")
            and block.get("alignment") != "right"
            and (match := LIST_MARKER_RE.match(text))
        ):
            candidates.append((block, text, match))
    if len(candidates) < 2 or any(
        int(match[1]) != number for number, (_, _, match) in enumerate(candidates, 1)
    ):
        return result
    for block, text, match in candidates:
        normalized = f"{int(match[1])}. " + text[match.end() :]
        block["runs"] = replace_run_text(block["runs"], normalized)
        if text != normalized and report is not None:
            report.record_change(
                "numbered_list_marker_normalized", member, 1, text, normalized
            )
    return result


def normalize_subheadings(
    blocks: list[dict],
    *,
    member: str = "chapter",
    report: NormalizationReport | None = None,
) -> list[dict]:
    """Prepare numbered section headings without changing any prose or separators."""
    result = copy.deepcopy(blocks)
    candidates = []
    for index, block in enumerate(result):
        text = block_text(block).strip()
        if (
            block["kind"] in {"paragraph", "heading"}
            and not block.get("variant")
            and block.get("alignment") != "right"
            and (match := SECTION_LABEL_RE.fullmatch(text))
        ):
            candidates.append((index, match["wrapped"] or match["bare"]))
    # A lone number, a list of adjacent numbers, or broken numbering is not
    # sufficient evidence. Require a complete 1..N sequence with prose per part.
    sequence = len(candidates) >= 2 and all(
        normalize_alphanumeric_width(label)
        in {str(number), format_chinese_numeral(number)}
        for number, (_, label) in enumerate(candidates, 1)
    )
    stops = [i for i, _ in candidates[1:]] + [len(result)]
    sequence = sequence and all(
        any(
            b["kind"] in {"paragraph", "quote"} and block_text(b).strip()
            for b in result[start + 1 : stop]
        )
        for (start, _), stop in zip(candidates, stops)
    )
    promote = {i for i, _ in candidates} if sequence else set()
    for index, block in enumerate(result):
        text = block_text(block).strip()
        if block.get("variant") == "original":
            continue
        if (
            index in promote
            or block["kind"] == "heading"
            and (SECTION_LABEL_RE.fullmatch(text) or NUMBERED_HEADING_RE.match(text))
        ):
            normalized = re.sub(
                r"^([（(第]?)([0-9０-９]+)",
                lambda match: match[1] + format_chinese_numeral(int(match[2])),
                text,
                count=1,
            )
            changed = (block["kind"], block.get("level"), block.get("alignment")) != (
                "heading",
                3,
                "center",
            ) or normalized != text
            block.update(kind="heading", level=3, alignment="center")
            block["runs"] = replace_run_text(block["runs"], normalized)
            if changed and report is not None:
                report.record_change(
                    "numbered_subheading_normalized",
                    member,
                    1,
                    text,
                    f"centered H3: {normalized}",
                )
    trimmed = trim_subheading_gaps(result)
    if report is not None:
        report.record_change(
            "subheading_empty_removed",
            member,
            len(result) - len(trimmed),
            "empty paragraphs around numbered heading",
            "",
        )
    return trimmed


def trim_subheading_gaps(blocks: list[dict]) -> list[dict]:
    """Numbered sections use heading spacing, never adjacent empty paragraphs."""

    def numbered(block):
        text = block_text(block).strip()
        return (
            block["kind"] == "heading"
            and block.get("variant") != "original"
            and (SECTION_LABEL_RE.fullmatch(text) or NUMBERED_HEADING_RE.match(text))
        )

    result = []
    index = 0
    while index < len(blocks):
        if not removable_empty_paragraph(blocks[index]):
            result.append(blocks[index])
            index += 1
            continue
        end = index
        while end < len(blocks) and removable_empty_paragraph(blocks[end]):
            end += 1
        if not (
            (index > 0 and numbered(blocks[index - 1]))
            or (end < len(blocks) and numbered(blocks[end]))
        ):
            result.extend(blocks[index:end])
        index = end
    return result


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


def normalize_chapter(
    chapter: dict, *, member: str = "chapter", report: NormalizationReport | None = None
) -> dict:
    report = report or NormalizationReport(path=Path("content"), applied=True)
    result = copy.deepcopy(chapter)
    result["title"] = normalize_text(
        result["title"], title=True, member=member, report=report
    )
    blocks = []
    prepared = normalize_list_markers(result["blocks"], member=member, report=report)
    for block in normalize_subheadings(prepared, member=member, report=report):
        if block.get("variant") == "original":
            blocks.append(block)
            continue
        text = block_text(block)
        normalized = normalize_text(
            text, title=block["kind"] == "heading", member=member, report=report
        )
        normalized = normalized.lstrip(" \t\u3000")
        block["runs"] = replace_run_text(block["runs"], normalized)
        if block["kind"] == "heading" or (
            block["kind"] == "paragraph"
            and block.get("alignment") == "center"
            and block["runs"]
            and all("bold" in r["styles"] for r in block["runs"])
        ):
            block.update(kind="heading", level=3)
        if block["kind"] == "paragraph":
            if re.fullmatch(r"(?:\*\s*){3,}", normalized.strip()):
                block["runs"] = replace_run_text(block["runs"], "***")
                block["alignment"] = "center"
            elif DECORATIVE_END_MARKER_RE.fullmatch(normalized.strip()):
                block["alignment"] = "center"
        blocks.append(block)
    # Structural rules operate on block content, regardless of the source format.
    expanded = []
    for block in blocks:
        text = block_text(block)
        match = (
            AUTHOR_NOTE_HEADING_RE.search(text)
            if block["kind"] == "paragraph"
            and not block.get("variant")
            and not has_reference_identity(block)
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
        text = block_text(block)
        previous = blocks[-1] if blocks else {}
        before = block_text(previous)
        if (
            previous.get("kind") == block["kind"] == "paragraph"
            and not previous.get("variant")
            and not block.get("variant")
            and not has_reference_identity(previous)
            and not has_reference_identity(block)
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
    while blocks and removable_empty_paragraph(blocks[0]):
        blocks.pop(0)
        report.record_change(
            "chapter_leading_empty_removed", member, 1, "empty paragraph", ""
        )
    if result.get("role") != "intro":
        scan_content_issues(
            member,
            [
                block_text(b)
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

    book["sections"] = normalize_outline(book["sections"], report=report)
    if "volume_colors" in book:
        book["volume_colors"] = normalize_volume_colors(book["volume_colors"])
    return book, report.to_dict()
