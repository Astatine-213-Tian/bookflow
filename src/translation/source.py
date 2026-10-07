"""Translation views of shared book JSON; no crawler-specific snapshot format."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from src.content.html import is_scene_break_text
from src.content.outline import ordered_members
from src.content.prepared import load_prepared_source


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def load_source(directory: Path) -> dict:
    book = load_prepared_source(directory / "source.json")[0]
    if not book["metadata"]["language"].lower().startswith("en"):
        raise ValueError(
            "The current translation methods require English input; collection itself supports other languages"
        )
    return book


def translation_chapters(book: dict) -> dict[str, dict]:
    result = {
        key: book["chapters"][key]
        for key in ordered_members(book["sections"])
        if book["chapters"][key].get("role") != "intro"
    }
    for extra in book["extras"]:
        if not extra.get("id"):
            raise ValueError("Independent extras need stable IDs before translation")
        result[extra["id"]] = extra
    return result


def chapter_ids(book: dict) -> list[str]:
    return list(translation_chapters(book))


def source_entries(book: dict) -> list[dict]:
    return [
        {
            "id": key,
            "title": chapter["title"],
            "source_id": chapter.get("source", {}).get("id") or key,
            "source_url": chapter.get("source", {}).get("url", ""),
        }
        for key, chapter in translation_chapters(book).items()
    ]


def load_chapter(book: dict, chapter_id: str) -> dict:
    chapter = translation_chapters(book)[chapter_id]
    blocks = []
    paragraphs = []
    for original in chapter["blocks"]:
        text = "".join(r["text"] for r in original["runs"])
        if original["kind"] == "divider" or is_scene_break_text(text):
            blocks.append({"type": "separator", "content": copy.deepcopy(original)})
        elif text.strip():
            index = len(paragraphs)
            paragraphs.append({"index": index, "english": text})
            blocks.append(
                {
                    "type": "content",
                    "index": index,
                    "english": text,
                    "content": copy.deepcopy(original),
                }
            )
        else:
            blocks.append({"type": "empty", "content": copy.deepcopy(original)})
    return {
        "id": chapter_id,
        "title": chapter["title"],
        "paragraphs": paragraphs,
        "blocks": blocks,
    }


def load_comments(directory: Path, book: dict, chapter_id: str) -> list[dict]:
    path = directory / "evidence.json"
    if not path.exists():
        return []
    evidence = json.loads(path.read_text())
    return evidence.get("comments", {}).get(chapter_id, [])
