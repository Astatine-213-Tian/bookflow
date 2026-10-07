"""Apply explicit chapter-level changes to current content without touching other text."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from src.content.contract import override_metadata, validate_book, validate_change
from src.content.normalize import normalize_chapter
from src.content.normalization import NormalizationReport
from src.runtime.files import digest


def content_hash(value: dict) -> str:
    return digest(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def apply_changes(current: dict, change: dict) -> tuple[dict, dict]:
    validate_book(current)
    validate_change(change)
    if change["book_id"] != current["identifier"]:
        raise ValueError("Change targets another book")
    if not isinstance(change["operations"], list) or not change["operations"]:
        raise ValueError("Change has no operations")
    result = copy.deepcopy(current)
    report = NormalizationReport(path=Path("content"), applied=True)
    for op in change["operations"]:
        kind = op.get("kind")
        if kind in {"replace_chapter", "append_chapter", "append_extra"}:
            key = op["chapter_id"]
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", key):
                raise ValueError("Chapter ID must be stable and independent of paths")
            if kind == "replace_chapter":
                existing = result["chapters"].get(key)
                if existing is None or content_hash(existing) != op["expected_sha256"]:
                    raise ValueError(f"Target chapter changed: {key}")
                chapter = {**existing, **op["chapter"]}
                if "source" in op["chapter"]:
                    chapter["source"] = {
                        **existing.get("source", {}),
                        **op["chapter"]["source"],
                    }
            else:
                chapter = op["chapter"]
            chapter = normalize_chapter(chapter, member=key, report=report)
            if kind == "replace_chapter":
                result["chapters"][key] = chapter
            elif kind == "append_extra":
                chapter.update(id=key, role="extra")
                existing = next(
                    (x for x in result["extras"] if x.get("id") == key), None
                )
                if existing is not None:
                    if existing != chapter:
                        raise ValueError(
                            "Extra ID already exists with different content"
                        )
                else:
                    result["extras"].append(chapter)
            else:
                if key in result["chapters"]:
                    raise ValueError(f"Chapter ID already exists: {key}")
                anchor = op["after"]

                def insert(nodes, anchor=anchor, key=key):
                    for i, node in enumerate(nodes):
                        if node.get("member") == anchor:
                            nodes.insert(i + 1, {"member": key})
                            return True
                        if "children" in node and insert(node["children"]):
                            return True
                    return False

                if anchor is None:
                    result["sections"].insert(0, {"member": key})
                elif not insert(result["sections"]):
                    raise ValueError(f"Unknown insertion anchor: {anchor}")
                result["chapters"][key] = chapter
        elif kind == "set_outline":
            if content_hash(result["sections"]) != op["expected_sha256"]:
                raise ValueError("Outline changed")
            result["sections"] = copy.deepcopy(op["sections"])
        else:
            fields = op["fields"]
            if not isinstance(fields, dict):
                raise ValueError("Metadata fields must be an object")
            before = {key: result["metadata"].get(key) for key in fields}
            if content_hash(before) != op["expected_sha256"]:
                raise ValueError("Metadata changed")
            result["metadata"] = override_metadata(result["metadata"], fields)
    validate_book(result)
    return result, report.to_dict()
