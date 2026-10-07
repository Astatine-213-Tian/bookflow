"""Join reviewed translations to shared content JSON before output selection."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from src.content.prepared import load_prepared_source
from src.translation.source import chapter_ids, load_chapter, translation_chapters


def translated_blocks(
    chapter: dict, data: dict, *, source_language: str = "en"
) -> list[dict]:
    groups = data.get("groups")
    if groups is None:
        groups = [
            {"english_indices": [item["index"]], "paragraphs": [item["zh"]]}
            for item in data.get("translations", [])
            if item.get("zh")
        ]
    else:
        expected = [item["index"] for item in chapter["paragraphs"]]
        if [i for group in groups for i in group["english_indices"]] != expected:
            raise ValueError("Grouped translation must cover source exactly once")
    if any(
        not g["english_indices"]
        or not g["paragraphs"]
        or not all(p.strip() for p in g["paragraphs"])
        for g in groups
    ):
        raise ValueError("Empty alignment group")
    endings = {g["english_indices"][-1]: g["paragraphs"] for g in groups}
    result = []
    inside = False
    for block in chapter["blocks"]:
        if block["type"] != "content" and inside and data.get("groups"):
            raise ValueError("Alignment crosses a source scene separator")
        original = copy.deepcopy(block["content"])
        original.update(language=source_language, variant="original")
        result.append(original)
        if block["type"] == "content":
            index = block["index"]
            inside = index not in endings
            result.extend(
                {
                    "kind": "paragraph",
                    "runs": [{"text": text, "styles": []}],
                    "language": "zh-CN",
                    "variant": "translation",
                }
                for text in endings.get(index, [])
            )
    return result


def translated_source(
    snapshot_dir: Path,
    translations_dir: Path,
    *,
    title: str | None = None,
    author: str | None = None,
) -> tuple[dict, bytes | None, str]:
    book, cover, mime = load_prepared_source(snapshot_dir / "source.json")
    result = copy.deepcopy(book)
    targets = translation_chapters(result)
    for key in chapter_ids(book):
        path = translations_dir / f"{key}.json"
        data = json.loads(path.read_text()) if path.exists() else {}
        targets[key]["blocks"] = translated_blocks(
            load_chapter(book, key),
            data,
            source_language=book["metadata"]["language"],
        )
    result["metadata"]["language"] = "zh-CN"
    if title:
        result["metadata"]["title"] = title
    if author:
        result["metadata"]["creator"] = author
        if author != book["metadata"]["creator"]:
            result["metadata"].pop("creators", None)
    result["source_format"] = "translation"
    return result, cover, mime
