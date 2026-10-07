from __future__ import annotations

import re
from html import unescape
from pathlib import Path

SPACE_RE = re.compile(r"[ \t\u3000]+")
BLANK_RE = re.compile(r"\n{3,}")
DOMAIN_PLACEHOLDER_RE = re.compile(r"^[()\[\]（）【】\s•·.。ｃｏｍcomCOM]+$")
CHAPTER_AD_TAIL_RE = re.compile(r"吗[?？]请记住.*$")
SHORT_PROMO_RE = re.compile(r"^[^\u4e00-\u9fffA-Za-z0-9]{0,3}想看.{0,40}《[^》]+》$")
MIRROR_AD_MARKERS = (
    "提醒您最全",
    "最新章 节",
    "最新章节",
    "全网首发更新",
    "想看",
)


def _is_mirror_boilerplate_line(value: str) -> bool:
    if DOMAIN_PLACEHOLDER_RE.fullmatch(value):
        return True
    if SHORT_PROMO_RE.fullmatch(value):
        return True
    return (
        "域名" in value
        and "《" in value
        and any(marker in value for marker in MIRROR_AD_MARKERS)
    )


def clean_text_line(value: str) -> str:
    text = SPACE_RE.sub(" ", unescape(value)).strip()
    text = CHAPTER_AD_TAIL_RE.sub("", text).strip()
    if _is_mirror_boilerplate_line(text):
        return ""
    return text


def write_prepared_txt(book: dict, out_path: Path) -> None:
    """Render already prepared blocks without another cleanup or deduplication."""
    metadata = book["metadata"]
    sections = [
        metadata["title"],
        "作者：" + "、".join(metadata.get("creators") or [metadata["creator"]]),
    ]

    def add_chapter(chapter: dict) -> None:
        sections.append(
            "\n".join(
                [
                    chapter["title"],
                    *[
                        "***"
                        if block["kind"] == "divider"
                        else "".join(r["text"] for r in block["runs"])
                        for block in chapter["blocks"]
                    ],
                ]
            )
        )

    def add_sections(nodes: list[dict]) -> None:
        for node in nodes:
            if "children" in node:
                sections.append(node["title"])
                add_sections(node["children"])
            else:
                add_chapter(book["chapters"][node["member"]])

    add_sections(book["sections"])
    for chapter in book["extras"]:
        add_chapter(chapter)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
