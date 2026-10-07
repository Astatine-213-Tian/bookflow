"""Persist content JSON and verify local assets independently of destinations."""

from __future__ import annotations

import json
from pathlib import Path

from src.content.contract import validate_book
from src.runtime.files import digest, write_json


def load_prepared_source(path: Path) -> tuple[dict, bytes | None, str]:
    book = json.loads(path.read_text())
    validate_book(book)
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


def save_source(
    book: dict, path: Path, cover: bytes | None = None, mime: str = "image/jpeg"
) -> None:
    if cover is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(mime, "img")
        name = f"cover.{suffix}"
        (path.parent / name).write_bytes(cover)
        book["assets"] = {
            "cover": {"path": name, "mime": mime, "sha256": digest(cover)}
        }
    validate_book(book)
    write_json(path, book)
