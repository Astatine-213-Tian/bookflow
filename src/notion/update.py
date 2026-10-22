"""Read current editor content and apply explicit, resumable chapter changes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from notion_books import NotionBooks, content_matches

from src.content.blocks import content_signature
from src.content.changes import apply_changes, content_hash
from src.content.contract import SCHEMA, validate_book, validate_change
from src.notion.capabilities import validate_notion_content
from src.notion.content import (
    localize_chapter_links,
    checkpoint_page_ids,
    targets,
    write_content,
)
from src.notion.cms import STORAGE
from src.notion.upload import run_bounded, source_digest, upload_draft
from src.runtime.files import write_json

JOURNAL_VERSION = 3


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


async def read_current(
    checkpoint: dict,
    *,
    tools,
    allow_pending: bool = False,
    only: set[str] | None = None,
    fingerprints: dict[str, str] | None = None,
) -> dict:
    """Read editor content; `only` limits fresh reads to those chapter/extra IDs.

    Other rows keep their checkpoint copy, which still supplies link targets.
    `fingerprints` collects each fresh page's fingerprint by row ID.
    """
    book = content_from_checkpoint(checkpoint)
    reader = NotionBooks(tools, api=tools.call_api)
    for key, chapter in book["chapters"].items():
        row = checkpoint["chapters"][key]
        if not row.get("page_id"):
            if allow_pending:
                continue
            raise ValueError("Complete or recover the import before editing")
        if only is not None and key not in only:
            continue
        page = await reader.document(row["page_id"], "chapters")
        chapter["title"] = page.properties["title"]
        chapter["blocks"] = page.blocks
        if fingerprints is not None:
            fingerprints[key] = page.fingerprint
    for index, chapter in enumerate(book["extras"]):
        row = checkpoint["extras"][index]
        if not row.get("page_id"):
            if allow_pending:
                continue
            raise ValueError("Complete or recover the extras import first")
        if only is not None and chapter.get("id") not in only:
            continue
        page = await reader.document(row["page_id"], "extras")
        chapter["title"] = page.properties["title"]
        chapter["blocks"] = page.blocks
        if fingerprints is not None and chapter.get("id"):
            fingerprints[chapter["id"]] = page.fingerprint
    localize_chapter_links(book, checkpoint_page_ids(checkpoint))
    validate_book(book)
    return book


def _destination_book(content: dict, checkpoint: dict) -> dict:
    result = copy.deepcopy(content)
    pages = checkpoint_page_ids(checkpoint)
    from src.notion.content import content_rows

    for key, row in content_rows(result).items():
        if key in pages:
            row["page_id"] = pages[key]
    return result


def _differing_rows(book: dict, base: dict) -> dict:
    """Keep journals small: every chapter-write checkpoint rewrites the journal.

    Chapters equal to the import checkpoint are rebuilt from it on resume. Link
    localization can add a start anchor to an untouched chapter, so differing
    rows are kept, not only the targeted ones.
    """
    return {
        "chapters": {
            key: chapter
            for key, chapter in book["chapters"].items()
            if base["chapters"].get(key) != chapter
        },
        "extras": book["extras"],
        "sections": book["sections"],
    }


def _with_rows(base: dict, rows: dict) -> dict:
    result = copy.deepcopy(base)
    result["chapters"].update(copy.deepcopy(rows["chapters"]))
    result["extras"] = copy.deepcopy(rows["extras"])
    result["sections"] = copy.deepcopy(rows["sections"])
    return result


async def apply_update(state: Path, change: dict, config: dict, *, tools) -> dict:
    validate_change(change)
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
    # Only targeted rows can change, so only they are read and refreshed.
    touched = {op["chapter_id"] for op in change["operations"]}
    reader = NotionBooks(tools, api=tools.call_api)
    base = content_from_checkpoint(checkpoint)
    fingerprints: dict[str, str] = {}
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())
        if journal["request_sha256"] != signature:
            raise ValueError("Change ID reused with different instructions")
        if (
            journal["work_id"] != checkpoint.get("work_id")
            or journal["book_id"] != checkpoint["identifier"]
        ):
            raise ValueError("Change journal belongs to a different destination")
        if journal.get("complete"):
            return await read_current(checkpoint, tools=tools, only=touched)
        # Version 2 journals hold complete books, which the same overlay accepts.
        if journal.get("version") not in {2, JOURNAL_VERSION}:
            raise ValueError(
                "This write journal requires explicit reconciliation before the new manuscript writer can proceed"
            )
    else:
        current = await read_current(
            checkpoint, tools=tools, only=touched, fingerprints=fingerprints
        )
        candidate, report = apply_changes(current, change)
        validate_notion_content(candidate)
        journal = {
            "version": JOURNAL_VERSION,
            "request_sha256": signature,
            "work_id": checkpoint.get("work_id"),
            "book_id": checkpoint["identifier"],
            "before": _differing_rows(current, base),
            "candidate": _differing_rows(candidate, base),
            "normalization": report,
            "writes": {},
        }
        write_json(journal_path, journal)
    candidate = _with_rows(base, journal["candidate"])
    previous = _with_rows(base, journal["before"])
    replacements = [
        op for op in change["operations"] if op["kind"] == "replace_chapter"
    ]
    additions = any(op["kind"] != "replace_chapter" for op in change["operations"])
    # Persist new identities through the ordinary import workflow. Existing rows
    # stay verified, so this never applies replacement bodies outside their journal.
    if additions:
        for key, chapter in candidate["chapters"].items():
            if key in checkpoint["chapters"]:
                checkpoint["chapters"][key].update(chapter)
            else:
                checkpoint["chapters"][key] = copy.deepcopy(chapter)
        known = {chapter.get("id") for chapter in checkpoint["extras"]}
        for chapter in candidate["extras"]:
            if chapter.get("id") not in known:
                checkpoint["extras"].append(copy.deepcopy(chapter))
        checkpoint["sections"] = candidate["sections"]
        checkpoint["uploaded"] = False
        write_json(state, checkpoint)
        await upload_draft(checkpoint, state, config, tools=tools)
    destinations = targets(_destination_book(candidate, checkpoint))
    previous_targets = targets(_destination_book(previous, checkpoint))
    pages = {}

    async def replace(op: dict) -> None:
        key = op["chapter_id"]
        desired = candidate["chapters"][key]
        before = previous["chapters"][key]
        item = journal["writes"].setdefault(
            key,
            {
                **copy.deepcopy(desired),
                "page_id": checkpoint["chapters"][key]["page_id"],
            },
        )
        if item.get("content_write"):
            expected = ""
        elif key in fingerprints:
            # Read moments ago for this journal; the writer rejects any change since.
            expected = fingerprints[key]
        else:
            page = await reader.document(item["page_id"], "chapters")
            if page.properties["title"] not in {
                before["title"],
                desired["title"],
            } or not (
                content_matches(page.blocks, before["blocks"], previous_targets)
                or content_matches(page.blocks, desired["blocks"], destinations)
            ):
                raise ValueError(
                    f"Notion chapter changed since the task was prepared: {key}"
                )
            expected = page.fingerprint
        await write_content(
            reader, item, journal_path, journal, destinations, expected=expected
        )
        page = await reader.document(item["page_id"], "chapters")
        if not content_matches(
            page.blocks, desired["blocks"], destinations
        ) or page.properties["title"] not in {
            before["title"],
            desired["title"],
        }:
            raise ValueError(f"Concurrent edit: {key}")
        if page.properties["title"] != desired["title"]:
            await reader.write_properties(page, {"title": desired["title"]})
            page = await reader.document(item["page_id"], "chapters")
            if page.properties["title"] != desired["title"] or not content_matches(
                page.blocks, desired["blocks"], destinations
            ):
                raise ValueError(f"Notion update readback differs: {key}")
        checkpoint["chapters"][key].update(desired)
        checkpoint["chapters"][key]["verified"] = True
        write_json(state, checkpoint)
        pages[key] = page

    await run_bounded(replacements, replace)
    # Replacements reuse their verified readback; only additions are read again.
    fresh = await read_current(
        checkpoint, tools=tools, only=touched - set(pages)
    )
    for key, page in pages.items():
        fresh["chapters"][key].update(
            title=page.properties["title"], blocks=page.blocks
        )
    localize_chapter_links(fresh, checkpoint_page_ids(checkpoint))
    for key, chapter in fresh["chapters"].items():
        if key in touched:
            checkpoint["chapters"][key].update(chapter)
    for row, chapter in zip(checkpoint["extras"], fresh["extras"], strict=True):
        if chapter.get("id") in touched:
            row.update(chapter)
    checkpoint["source_sha256"] = source_digest(content_from_checkpoint(checkpoint))
    write_json(state, checkpoint)
    journal["complete"] = True
    write_json(journal_path, journal)
    return content_from_checkpoint(checkpoint)
