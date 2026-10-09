"""Normalize known volume labels without inferring or changing the outline."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from src.content.normalization import (
    NormalizationIssue,
    NormalizationReport,
    _normalize_plain_text,
    _normalize_title_periods,
    normalize_alphanumeric_width,
)
from src.content.numerals import format_chinese_numeral, parse_number

HAN_NUMBER = r"[零〇一二两三四五六七八九十百千万]+"
NUMBER = rf"(?:[0-9]+(?![0-9]|\.[0-9])|{HAN_NUMBER})"
SEPARATOR = r"[\s·.：:、—–-]"
VOLUME_NUMBER_RE = re.compile(
    rf"^(?:第\s*(?P<ordinal>{NUMBER})\s*卷|卷\s*(?P<number>"
    rf"[0-9]+(?![0-9]|\.[0-9])|{HAN_NUMBER}(?=$|{SEPARATOR})))"
)


def normalize_volume_title(
    text: str, *, member: str = "outline", report: NormalizationReport | None = None
) -> str:
    original = text
    text = normalize_alphanumeric_width(text).strip()
    match = VOLUME_NUMBER_RE.match(text)
    if match:
        number = parse_number(match["ordinal"] or match["number"])
        subtitle = re.sub(rf"^{SEPARATOR}+", "", text[match.end() :])
        text = f"卷{format_chinese_numeral(number)}"
        if subtitle:
            text += "·" + subtitle
    elif report is not None and re.match(rf"^卷\s*{HAN_NUMBER}", text):
        report.issues.append(
            NormalizationIssue(
                kind="ambiguous_volume_number",
                member=member,
                message="Volume number and subtitle have no unambiguous boundary.",
                excerpt=original,
                recommended_action="Review the source and supply a separated volume label.",
            )
        )
    # A volume label has its own numbering/separator policy. It must not pass
    # through the fanwai *chapter* prefix-removal rules. Record only net edits,
    # since ordinary Han/Latin spacing is projected to dots in this field.
    scratch = NormalizationReport(path=Path("content"), applied=True)
    text = _normalize_title_periods(text, member=member, report=scratch)
    text = _normalize_plain_text(
        text,
        preserve_ordinals=True,
        remove_han_spaces=False,
        title_punctuation=False,
        end_marker=False,
        force_fanwai_title=False,
        member=member,
        report=scratch,
    )
    # Protect the explicit volume token from ordinary Han/digit body spacing.
    text = re.sub(r"^卷\s+(?=[0-9])", "卷", text)
    text = re.sub(r"[\s·]+", "·", text).strip("·")
    if report is not None:
        report.record_change(
            "volume_title_normalized", member, int(text != original), original, text
        )
    return text


def normalize_outline(
    nodes: list[dict], *, report: NormalizationReport | None = None
) -> list[dict]:
    result = copy.deepcopy(nodes)

    def visit(items):
        for node in items:
            if "children" in node:
                node["title"] = normalize_volume_title(
                    node["title"], member=node.get("id", "outline"), report=report
                )
                visit(node["children"])

    visit(result)
    return result


def normalize_volume_colors(colors: dict[str, str]) -> dict[str, str]:
    result = {}
    for title, color in colors.items():
        title = normalize_volume_title(title)
        if title in result and result[title] != color:
            raise ValueError(f"Volume colors conflict after normalization: {title}")
        result[title] = color
    return result
