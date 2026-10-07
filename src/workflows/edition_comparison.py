"""Optional local edition comparison, independent of preparation and import."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from src.content.outline import ordered_members
from src.inputs.epub import InputBook
from src.inputs.load import read_input
from src.runtime.files import digest


def compare_editions(
    left: Path, right: Path, *, title: str = "", author: str = ""
) -> dict:
    editions = [read_input(path, title=title, author=author) for path in (left, right)]
    identities = [
        (e.source["metadata"]["title"], e.source["metadata"]["creator"])
        for e in editions
    ]
    if identities[0] != identities[1]:
        raise ValueError("Edition title/author identities differ")

    def lines(edition: InputBook) -> list[str]:
        book = edition.source
        chapters = [
            book["chapters"][m] for m in ordered_members(book["sections"])
        ] + book["extras"]
        return [
            re.sub(r"\s+", " ", "".join(run["text"] for run in block["runs"])).strip()
            for chapter in chapters
            for block in chapter["blocks"]
        ]

    a, b = map(lines, editions)
    opcodes = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    kinds = {tag for tag, *_ in opcodes if tag != "equal"}
    selected = None
    if not kinds:
        selected = (
            right
            if right.suffix.lower() == ".epub" and left.suffix.lower() != ".epub"
            else left
        )
    elif kinds == {"delete"}:
        selected = left
    elif kinds == {"insert"}:
        selected = right
    return {
        "title": identities[0][0],
        "author": identities[0][1],
        "files": [
            {
                "path": str(path),
                "sha256": digest(path.read_bytes()),
                "paragraphs": len(body),
                "chapters": len(e.source["chapters"]),
                "extras": len(e.source["extras"]),
            }
            for path, body, e in zip((left, right), (a, b), editions, strict=True)
        ],
        "selected": str(selected) if selected else None,
        "reason": "same paragraph text; prefer EPUB when available"
        if not kinds
        else "ordered paragraph containment"
        if selected
        else "both editions contain unique text; review differences",
        "differences": [
            {
                "kind": tag,
                "left_paragraphs": [i, j],
                "right_paragraphs": [k, l],
                "left_excerpt": a[i:j][:3],
                "right_excerpt": b[k:l][:3],
            }
            for tag, i, j, k, l in opcodes
            if tag != "equal"
        ],
    }
