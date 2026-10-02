"""Load the persisted prepared-book contract and its local cover asset."""

from __future__ import annotations

import json
from pathlib import Path

from notion_books import from_markdown, to_markdown

from src.content.blocks import content_signature
from src.content.outline import ordered_members
from src.runtime.files import digest


def load_prepared_source(path: Path) -> tuple[dict, bytes | None, str]:
    book = json.loads(path.read_text())
    if book.get("version") != 2 or not book.get("identifier"):
        raise ValueError("Expected a version 2 prepared book with an identifier")
    for field in ("title", "creator"):
        if (
            not isinstance(book["metadata"].get(field), str)
            or not book["metadata"][field].strip()
        ):
            raise ValueError(f"Prepared book requires metadata.{field}")
    members = ordered_members(book["sections"])
    if len(members) != len(set(members)) or set(members) != set(book["chapters"]):
        raise ValueError("Prepared outline must include each chapter exactly once")
    for chapter in [*book["chapters"].values(), *book["extras"]]:
        if not chapter.get("title"):
            raise ValueError("Prepared chapter has no title")
        blocks = chapter["blocks"]
        if content_signature(from_markdown(to_markdown(blocks))) != content_signature(
            blocks
        ):
            raise ValueError(f"Prepared content cannot roundtrip: {chapter['title']}")
    asset = book.get("assets", {}).get("cover")
    if not asset:
        return book, None, "image/jpeg"
    member = (path.parent / asset["path"]).resolve()
    if not member.is_relative_to(path.parent.resolve()):
        raise ValueError("Prepared cover must stay inside the preparation directory")
    data = member.read_bytes()
    if digest(data) != asset["sha256"]:
        raise ValueError("Prepared cover asset changed")
    return book, data, asset["mime"]
