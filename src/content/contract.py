"""The shared, destination-independent JSON contract."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.content.outline import ordered_members

SCHEMA_PATH = Path(__file__).with_name("book.schema.json")
SCHEMA = json.loads(SCHEMA_PATH.read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def validate_book(book: dict) -> None:
    error = next(iter(VALIDATOR.iter_errors(book)), None)
    if error:
        location = ".".join(map(str, error.absolute_path)) or "book"
        raise ValueError(f"Invalid content at {location}: {error.message}")
    members = ordered_members(book["sections"])
    if len(members) != len(set(members)) or set(members) != set(book["chapters"]):
        raise ValueError("Outline must reference each chapter exactly once")
    if not members and not book["extras"]:
        raise ValueError("Book has no readable content")
    identities = list(book["chapters"]) + [
        x["id"] for x in book["extras"] if x.get("id")
    ]

    def collect_ids(nodes):
        for node in nodes:
            if "children" in node:
                if node.get("id"):
                    identities.append(node["id"])
                collect_ids(node["children"])

    collect_ids(book["sections"])
    if len(identities) != len(set(identities)):
        raise ValueError("Content identities must be unique")
    for chapter in [*book["chapters"].values(), *book["extras"]]:
        for block in chapter["blocks"]:
            if block["kind"] == "divider" and block["runs"]:
                raise ValueError("Divider must not contain text")
            if block["kind"] != "heading" and "level" in block:
                raise ValueError("Only headings have a level")

    from src.content.references import validate_references

    validate_references(book)


def metadata_defaults(metadata: dict) -> dict:
    return {
        "title": "",
        "creator": "",
        "language": "und",
        "date": "",
        "source": "",
        "description": "",
        "subjects": [],
        "series": "",
        "series_position": "",
        **metadata,
    }


def override_metadata(current: dict, fields: dict) -> dict:
    """An explicit primary-author override replaces any inherited author list."""
    result = {**current, **fields}
    if "creator" in fields and "creators" not in fields:
        result.pop("creators", None)
    return result


def validate_change(change: dict) -> None:
    validator = Draft202012Validator(
        {"$defs": SCHEMA["$defs"], "$ref": "#/$defs/change"}
    )
    error = next(iter(validator.iter_errors(change)), None)
    if error:
        raise ValueError(f"Invalid change: {error.message}")
    targets = [op["chapter_id"] for op in change["operations"] if "chapter_id" in op]
    if len(targets) != len(set(targets)):
        raise ValueError("Each chapter may be changed once per task")
