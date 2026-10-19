"""Recover reviewed translations from a bilingual EPUB this repository wrote."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from src.content.html import is_scene_break_text
from src.translation.source import clean_text

XHTML = "{http://www.w3.org/1999/xhtml}"


def _text(element: ET.Element) -> str:
    return "".join(element.itertext())


def chapter_groups(chapter: ET.Element) -> dict:
    """English paragraphs and alignment groups, or the reason they can't be read.

    The writer emits each source block as ``data-variant="original"`` and the
    group's Chinese paragraphs right after the last English paragraph it covers.
    """
    english: list[str] = []
    groups: list[dict] = []
    current: dict | None = None
    for element in chapter:
        variant = element.get("data-variant")
        if variant == "original":
            text = _text(element)
            if element.tag in (f"{XHTML}hr", "hr") or is_scene_break_text(text):
                text = ""
            if not text.strip():
                if current is not None and not current["paragraphs"]:
                    return {"error": "untranslated paragraph before a separator"}
                current = None
                continue
            if current is None or current["paragraphs"]:
                current = {"english_indices": [], "paragraphs": []}
                groups.append(current)
            current["english_indices"].append(len(english))
            english.append(text)
        elif variant == "translation":
            if current is None:
                return {"error": "translation without English"}
            current["paragraphs"].append(_text(element))
    if any(not group["paragraphs"] for group in groups):
        return {"error": "untranslated paragraph"}
    if any(not text.strip() for g in groups for text in g["paragraphs"]):
        return {"error": "empty translation"}
    return {"english": english, "groups": groups}


def read_bilingual_epub(path: Path) -> dict[str, dict]:
    """Map each chapter ID in the EPUB to its ``chapter_groups`` result."""
    chapters: dict[str, dict] = {}
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith(".xhtml"):
                continue
            root = ET.fromstring(archive.read(name))
            for element in root.iter():
                chapter_id = element.get("data-book-chapter-id")
                if chapter_id:
                    chapters[chapter_id] = chapter_groups(element)
    return chapters


def matching_groups(expected: list[str], recovered: dict) -> list[dict] | None:
    """The recovered groups when their English is exactly the expected text."""
    if "error" in recovered:
        return None
    if [clean_text(x) for x in recovered["english"]] != [
        clean_text(x) for x in expected
    ]:
        return None
    return recovered["groups"]
