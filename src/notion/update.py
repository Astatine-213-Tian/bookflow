"""Read current editor content and apply explicit, resumable chapter changes."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

from notion_books import FIELDS, NotionBooks, to_markdown

from src.content.blocks import content_signature
from src.content.changes import apply_changes, content_hash
from src.content.contract import SCHEMA, validate_book, validate_change
from src.notion.capabilities import read_content, validate_notion_content
from src.notion.references import (
    plain_references,
    finish_references,
    expected_content,
    localize_chapter_links,
    checkpoint_page_ids,
)
from src.notion.cms import STORAGE
from src.notion.upload import source_digest, upload_draft
from src.runtime.files import write_json


def content_from_checkpoint(checkpoint: dict) -> dict:
    book = {
        k: copy.deepcopy(v) for k, v in checkpoint.items() if k in SCHEMA["properties"]
    }
    chapter_fields = set(SCHEMA["$defs"]["chapter"]["properties"])
    book["chapters"] = {
        k: {field: value for field, value in ch.items() if field in chapter_fields}
        for k, ch in book["chapters"].items()
    }
    book["extras"] = [
        {field: value for field, value in ch.items() if field in chapter_fields}
        for ch in book["extras"]
    ]
    book.pop(
        "assets", None
    )  # Remote cover is managed separately from the content export.
    validate_book(book)
    return book


async def read_current(checkpoint: dict, *, tools, allow_pending: bool = False) -> dict:
    book = content_from_checkpoint(checkpoint)
    reader = NotionBooks(tools)
    for key, chapter in book["chapters"].items():
        row = checkpoint["chapters"][key]
        if not row.get("page_id"):
            if allow_pending:
                continue
            raise ValueError("Complete or recover the import before editing")
        page = await reader.document(row["page_id"])
        chapter["title"] = page.properties[FIELDS["chapter_title"]]
        chapter["blocks"] = read_content(page.markdown)
    for index, chapter in enumerate(book["extras"]):
        row = checkpoint["extras"][index]
        if not row.get("page_id"):
            if allow_pending:
                continue
            raise ValueError("Complete or recover the extras import first")
        page = await reader.document(row["page_id"])
        chapter["title"] = page.properties[FIELDS["extra_title"]]
        chapter["blocks"] = read_content(page.markdown)
    localize_chapter_links(book, checkpoint_page_ids(checkpoint))
    validate_book(book)
    return book


async def apply_update(state: Path, change: dict, config: dict, *, tools) -> dict:
    validate_change(change)
    # This adapter implements content edits. Catalog/outline changes are explicit
    # separate operations and cannot silently degrade into content-only writes.
    if any(
        op.get("kind") not in {"replace_chapter", "append_chapter", "append_extra"}
        for op in change.get("operations", [])
    ):
        raise ValueError(
            "Notion updates support chapter replacements/additions and independent extras"
        )
    checkpoint = json.loads(state.read_text())
    if (
        checkpoint.get("storage") != STORAGE
        or checkpoint.get("catalog_id")
        != config["databases"]["works"]["data_source_id"]
    ):
        raise ValueError("Not a checkpoint for this CMS catalog")
    journal_path = state.parent / "changes" / f"{change['id']}.json"
    signature = content_hash(change)
    current = await read_current(
        checkpoint, tools=tools, allow_pending=journal_path.exists()
    )
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())
        if journal["request_sha256"] != signature:
            raise ValueError("Change ID reused with different instructions")
        if (
            journal["work_id"] != checkpoint.get("work_id")
            or journal["book_id"] != checkpoint["identifier"]
        ):
            raise ValueError("Change journal belongs to a different destination")
        candidate = journal["candidate"]
        if journal.get("complete"):
            return (
                current  # A completed task never overwrites subsequent editor changes.
            )
    else:
        candidate, report = apply_changes(current, change)
        validate_notion_content(candidate)
        journal = {
            "request_sha256": signature,
            "work_id": checkpoint.get("work_id"),
            "book_id": checkpoint["identifier"],
            "before": current,
            "candidate": candidate,
            "normalization": report,
            "written": [],
        }
        write_json(journal_path, journal)
    reader = NotionBooks(tools)
    replacements = [
        op for op in change["operations"] if op["kind"] == "replace_chapter"
    ]

    def compatible(actual, before, after):
        # Body and title are separate remote writes. Either may have completed
        # before a timeout; a third value is an editor change and must stop us.
        return actual["title"] in {
            before["title"],
            after["title"],
        } and content_signature(actual["blocks"]) in [
            content_signature(before["blocks"]),
            content_signature(after["blocks"]),
            content_signature(plain_references(after["blocks"])),
        ]

    for op in replacements:
        key = op["chapter_id"]
        if not compatible(
            current["chapters"][key],
            journal["before"]["chapters"][key],
            candidate["chapters"][key],
        ):
            raise ValueError(
                f"Notion chapter changed since the task was prepared: {key}"
            )

    def page_content(page, key):
        scope = copy.deepcopy(current)
        scope["chapters"][key]["blocks"] = read_content(page.markdown)
        localize_chapter_links(scope, checkpoint_page_ids(checkpoint))
        return scope["chapters"][key]["blocks"]

    for op in replacements:
        key = op["chapter_id"]
        desired = candidate["chapters"][key]
        page_id = checkpoint["chapters"][key]["page_id"]
        page = await reader.document(page_id)
        actual = {
            "title": page.properties[FIELDS["chapter_title"]],
            "blocks": page_content(page, key),
        }
        if not compatible(actual, journal["before"]["chapters"][key], desired):
            raise ValueError(f"Concurrent edit: {key}")
        if content_signature(actual["blocks"]) != content_signature(desired["blocks"]):
            await reader.replace_content(
                page_id,
                replace(
                    page,
                    markdown=to_markdown(plain_references(desired["blocks"])),
                    blocks=None,
                ),
            )
        if actual["title"] != desired["title"]:
            page = await reader.document(page_id)
            if page.properties[FIELDS["chapter_title"]] not in {
                actual["title"],
                desired["title"],
            } or content_signature(page_content(page, key)) not in [
                content_signature(desired["blocks"]),
                content_signature(plain_references(desired["blocks"])),
            ]:
                raise ValueError(f"Concurrent edit: {key}")
            await reader.write_properties(
                page_id, {FIELDS["chapter_title"]: desired["title"]}
            )
        actual = await reader.document(page_id)
        if actual.properties[FIELDS["chapter_title"]] != desired[
            "title"
        ] or content_signature(page_content(actual, key)) not in [
            content_signature(desired["blocks"]),
            content_signature(plain_references(desired["blocks"])),
        ]:
            raise ValueError(f"Notion update readback differs: {key}")
        if key not in journal["written"]:
            journal["written"].append(key)
        write_json(journal_path, journal)
    # Existing rows keep their transport IDs; additions go through the ordinary
    # duplicate review, pending-create checkpoint and full readback machinery.
    for key, chapter in current["chapters"].items():
        checkpoint["chapters"][key].update(chapter)
    for index, chapter in enumerate(current["extras"]):
        checkpoint["extras"][index].update(chapter)
    for op in change["operations"]:
        key = op["chapter_id"]
        if op["kind"] == "replace_chapter":
            checkpoint["chapters"][key].update(candidate["chapters"][key])
        elif op["kind"] == "append_chapter":
            checkpoint["chapters"].setdefault(key, candidate["chapters"][key])
        elif not any(x.get("id") == key for x in checkpoint["extras"]):
            checkpoint["extras"].append(
                next(x for x in candidate["extras"] if x.get("id") == key)
            )
    checkpoint["sections"] = candidate["sections"]
    additions = any(op["kind"] != "replace_chapter" for op in change["operations"])
    if additions:
        checkpoint["uploaded"] = False
    write_json(state, checkpoint)
    if additions:
        await upload_draft(checkpoint, state, config, tools=tools)
    if not additions:
        await finish_references(checkpoint, state, tools=tools)
    for op in replacements:
        item = checkpoint["chapters"][op["chapter_id"]]
        page = await reader.document(item["page_id"])
        if content_signature(read_content(page.markdown)) != content_signature(
            expected_content(item["blocks"], checkpoint.get("reference_bindings", {}))
        ):
            raise ValueError("Final reference readback differs")
    checkpoint["source_sha256"] = source_digest(content_from_checkpoint(checkpoint))
    write_json(state, checkpoint)
    journal["complete"] = True
    write_json(journal_path, journal)
    return content_from_checkpoint(checkpoint)
