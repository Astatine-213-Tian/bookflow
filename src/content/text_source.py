"""Read explicitly numbered local TXT editions without deduplicating prose."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from src.runtime.files import digest

HEADING = re.compile(
    r"^(?:第\d+章(?:\s.*)?|番外(?:[一二三四五六七八九十百零\d]+(?:[·：:\s].*)?)?)$"
)


def read_txt_source(path: Path, *, title: str = "", author: str = "") -> dict:
    data = path.read_bytes()
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError as error:
        raise ValueError(
            "TXT must be UTF-8 or BOM-marked UTF-16; convert a copy first"
        ) from error
    lines = [line.strip() for line in text.splitlines()]
    headings = [i for i, line in enumerate(lines) if HEADING.fullmatch(line)]
    if not headings:
        raise ValueError(
            "TXT requires explicit 第N章 headings; supply an EPUB or review its structure"
        )
    front = [line for line in lines[: headings[0]] if line]
    if front and not title:
        title = front[0]
    if front and front[0] == title:
        front.pop(0)
    if front and front[0].startswith("作者："):
        found = front.pop(0)[3:].strip()
        if author and author != found:
            raise ValueError("TXT author header disagrees with --author")
        author = found
    if not title or not author:
        raise ValueError("TXT requires title/author headers or --title and --author")
    if front and front[0] == "简介":
        front.pop(0)
    source = {
        "version": 2,
        "identifier": str(uuid5(NAMESPACE_URL, "local-txt:" + digest(data))),
        "source_format": "txt",
        "metadata": {
            "title": title,
            "creator": author,
            "language": "zh-CN",
            "source": "",
            "date": "",
            "description": "\n".join(front),
            "subjects": [],
            "series": "",
            "series_position": "",
        },
        "sections": [],
        "chapters": {},
        "extras": [],
    }

    def chapter(name: str, paragraphs: list[str], role: str = "chapter") -> dict:
        return {
            "title": name,
            "role": role,
            "blocks": [
                {"kind": "paragraph", "runs": [{"text": line, "styles": []}]}
                for line in paragraphs
                if line
            ],
        }

    if front:
        source["chapters"]["EPUB/intro.xhtml"] = chapter("简介", front, "intro")
        source["sections"].append({"member": "EPUB/intro.xhtml"})
    for index, start in enumerate(headings):
        end = headings[index + 1] if index + 1 < len(headings) else len(lines)
        member = f"EPUB/chap_01_{index + 1:03d}.xhtml"
        value = chapter(lines[start], lines[start + 1 : end])
        if lines[start].startswith("番外"):
            source["extras"].append(value)
        elif source["extras"]:
            raise ValueError(
                "TXT resumes numbered chapters after independent extras; review the outline"
            )
        else:
            source["chapters"][member] = value
            source["sections"].append({"member": member})
    return source
