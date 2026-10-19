"""Snapshot existing books and apply small, resumable edits to existing blocks.

The shared reader owns manuscript decoding. This adapter never re-encodes a
chapter: it inserts empty paragraphs or patches the text of an existing native
paragraph, retaining its rich-text annotations and every untouched block ID.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

from notion_books import NotionBooks, notion_id

from src.content.blocks import block_text, replace_run_text
from src.content.contract import metadata_defaults, validate_book
from src.content.proofread import chapters
from src.content.quote_review import review_fingerprint
from src.runtime.files import write_json

# Snapshots written before property IDs recorded the title column's display name.
LEGACY_TITLE_FIELDS = {"章节": "chapters", "番外": "extras"}


def outline_identity(rows: list[dict]) -> list[dict]:
    return [
        {k: row[k] for k in ("page_id", "title", "parent_title", "extra")}
        for row in rows
    ]


async def snapshot_book(
    work: str, config: dict, output: Path, *, tools
) -> tuple[dict, dict]:
    reader = NotionBooks(tools, api=tools.call_api)
    work_id = notion_id(work)
    databases = config["databases"]
    extras_source = databases["extras"]["data_source_id"]
    source = await reader.discover(
        work_id,
        [databases["works"]["data_source_id"]],
        extras_source,
        view_policy="editorial",
    )
    if not source.get("chapters_view"):
        raise ValueError("Book has no complete editorial chapter view")
    if source.get("extras_view") and not source.get("extras_view_complete"):
        raise ValueError("Extras view is incomplete")
    outline = await reader.outline(source, extras_source, view_policy="editorial")
    page = await reader.page(work_id, "works")
    book = {
        "version": 3,
        "identifier": f"notion:{work_id}",
        "source_format": "notion",
        "metadata": metadata_defaults(
            {
                "title": page.properties["title"],
                "source": page.properties.get("source", ""),
                "language": "zh-CN",
            }
        ),
        "chapters": {},
        "sections": [],
        "extras": [],
    }
    evidence = {
        "work_id": work_id,
        "discovery": source,
        "extras_source": extras_source,
        "outline": outline_identity(outline),
        "pages": {},
    }
    semaphore = asyncio.Semaphore(5)

    async def read(row):
        async with semaphore:
            kind = "extras" if row["extra"] else "chapters"
            document = await reader.document(row["page_id"], kind)
            expected_ds = (
                extras_source if row["extra"] else source["chapters_data_source"]
            )
            if (
                document.data_source_id != expected_ds
                or document.properties.get("title") != row["title"]
            ):
                raise ValueError("Chapter identity changed while snapshotting")
            print(f"Notion read: {row['title']}", flush=True)
            return row, document, kind

    rows = await asyncio.gather(*(read(row) for row in outline))
    for ordinal, (row, document, kind) in enumerate(rows):
        chapter = {"title": row["title"], "blocks": document.blocks}
        if row["extra"]:
            member = f"extra:{len(book['extras'])}"
            chapter["id"] = f"extra-{len(book['extras'])}"
            book["extras"].append(chapter)
        else:
            member = f"chapter-{ordinal + 1:04d}"
            book["chapters"][member] = chapter
            parent = row["parent_title"]
            if parent:
                if not book["sections"] or book["sections"][-1].get("title") != parent:
                    book["sections"].append({"title": parent, "children": []})
                book["sections"][-1]["children"].append({"member": member})
            else:
                book["sections"].append({"member": member})
        evidence["pages"][member] = {
            "page_id": document.page_id,
            "data_source_id": document.data_source_id,
            "title": row["title"],
            "kind": kind,
            "native": document.native,
            "fingerprint": document.fingerprint,
        }
    if (
        outline_identity(
            await reader.outline(source, extras_source, view_policy="editorial")
        )
        != evidence["outline"]
    ):
        raise ValueError("Book outline changed while snapshotting")
    validate_book(book)
    write_json(output / "source.json", book)
    write_json(output / "evidence.json", evidence)
    return book, evidence


def page_kind(saved: dict) -> str:
    # Evidence is part of a journal's fingerprint, so legacy files are read as is.
    if "kind" in saved:
        return saved["kind"]
    if saved.get("title_field") in LEGACY_TITLE_FIELDS:
        return LEGACY_TITLE_FIELDS[saved["title_field"]]
    raise ValueError("Snapshot evidence has no page kind; take a new snapshot")


def native_equal(
    actual: list[dict], expected: list[dict], *, new_ids: bool = False
) -> bool:
    if len(actual) != len(expected):
        return False
    for a, b in zip(actual, expected):
        if b.get("id") and a.get("id") != b["id"]:
            return False
        if not b.get("id") and not new_ids:
            return False
        if (
            a.get("kind") != b.get("kind")
            or a.get("runs", []) != b.get("runs", [])
            or a.get("width", 0) != b.get("width", 0)
            or a.get("list_start", 0) != b.get("list_start", 0)
            or not native_equal(
                a.get("children", []), b.get("children", []), new_ids=new_ids
            )
        ):
            return False
    return True


def expected_edit(native: list[dict], block_id: str, operation: dict) -> list[dict]:
    after = copy.deepcopy(native)
    if operation["kind"] == "append_note":
        after.extend(
            {"id": "", "kind": b["kind"], "runs": b["runs"]}
            for b in operation["blocks"]
        )
        return after
    indexes = [i for i, block in enumerate(after) if block["id"] == block_id]
    if len(indexes) != 1:
        raise ValueError("Target block disappeared")
    i = indexes[0]
    if operation["kind"] == "insert_divider":
        after.insert(i + 1, {"id": "", "kind": "divider", "runs": []})
        return after
    if after[i]["kind"] != "paragraph" or after[i].get("children"):
        raise ValueError("Proofread edits require a flat paragraph")
    if operation["kind"] == "insert_blank":
        if not 1 <= operation["count"] <= 100:
            raise ValueError("Unexpected reference gap size")
        after[i + 1 : i + 1] = [
            {"id": "", "kind": "paragraph", "runs": []}
            for _ in range(operation["count"])
        ]
    elif operation["kind"] == "insert_note":
        after[i + 1 : i + 1] = [
            {"id": "", "kind": b["kind"], "runs": b["runs"]}
            for b in operation["blocks"]
        ]
    else:
        if block_text(after[i]) != operation["before"]:
            raise ValueError("Text changed since review")
        after[i]["runs"] = replace_run_text(
            after[i].get("runs", []), operation["after"]
        )
    return after


def text_payload(raw: dict, before: str, after: str) -> dict:
    """Patch existing REST text objects, without converting portable manuscript runs."""
    if raw.get("type") != "paragraph" or raw.get("has_children"):
        raise ValueError("Text edit requires a plain native paragraph")
    rich = raw["paragraph"]["rich_text"]
    if any(run.get("type") != "text" for run in rich):
        raise ValueError(
            "A mention/equation requires the full manuscript update workflow"
        )
    if "".join(run["text"]["content"] for run in rich) != before:
        raise ValueError("Text changed immediately before mutation")
    runs = replace_run_text(
        [{"text": run["text"]["content"], "native": run} for run in rich], after
    )
    desired = []
    for run in runs:
        item = copy.deepcopy(run["native"])
        item.pop("plain_text", None)
        item.pop("href", None)
        if len(run["text"]) > 2000:
            raise ValueError("Text edit exceeds native run limit")
        item["text"]["content"] = run["text"]
        desired.append(item)
    return {"paragraph": {"rich_text": desired}}


def append_payload(blocks: list[dict]) -> list[dict]:
    """The delta endpoint supports only empty blocks and plain-text author notes."""
    if not 1 <= len(blocks) <= 100:
        raise ValueError("Author note exceeds the single append batch limit")
    result = []
    for block in blocks:
        if block["kind"] == "divider" and not block.get("runs"):
            result.append({"object": "block", "type": "divider", "divider": {}})
            continue
        if block["kind"] != "paragraph" or any(
            r.get("styles") or r.get("href") for r in block.get("runs", [])
        ):
            raise ValueError("Author notes require plain text")
        text = block_text(block)
        if len(text) > 2000:
            raise ValueError("Author-note paragraph exceeds the native text limit")
        result.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                    if text
                    else []
                },
            }
        )
    return result


def acknowledge_append(
    response: dict, before: list[dict], after: list[dict]
) -> list[dict]:
    pending = [i for i, b in enumerate(after) if not b.get("id")]
    rows = response.get("results")
    # The 2025 API's `after` response can include existing following siblings.
    # Bind only new identities; the bounded full readback verifies their position.
    ids = {b["id"] for b in before}
    if isinstance(rows, list):
        returned_ids = [notion_id(row["id"]) for row in rows]
        if len(set(returned_ids)) != len(returned_ids):
            raise ValueError("Append response contains duplicate identities")
        rows = [row for row, id in zip(rows, returned_ids) if id not in ids]
    if (
        response.get("object") != "list"
        or not isinstance(rows, list)
        or len(rows) != len(pending)
    ):
        raise ValueError(
            "Append response omitted complete identities; resume from the journal: "
            + repr(
                {
                    "object": response.get("object"),
                    "rows": len(rows) if isinstance(rows, list) else None,
                    "expected": len(pending),
                    "has_more": response.get("has_more"),
                    "next_cursor": response.get("next_cursor"),
                }
            )
        )
    expected = copy.deepcopy(after)
    for i, row in zip(pending, rows):
        block = expected[i]
        id = notion_id(row["id"])
        kind = row.get("type")
        if (
            id in ids
            or row.get("object") != "block"
            or row.get("has_children") is not False
            or kind != block["kind"]
        ):
            raise ValueError("Append returned unexpected block identities")
        rich = row.get(kind, {}).get("rich_text", [])
        if (
            any(r.get("type") != "text" or r.get("text", {}).get("link") for r in rich)
            or "".join(r["text"]["content"] for r in rich) != block_text(block)
            or any(
                any(
                    value
                    for key, value in r.get("annotations", {}).items()
                    if key != "color"
                )
                or r.get("annotations", {}).get("color", "default") != "default"
                for r in rich
            )
        ):
            raise ValueError("Append response differs from the requested plain text")
        block["id"] = id
        ids.add(id)
    return expected


async def checked_api(tools, request: dict) -> dict:
    result = await tools.call_api(request)
    if not 200 <= result["status"] < 300:
        raise ValueError(
            f"Notion {request['method']} failed (HTTP {result['status']}); resume the saved journal"
        )
    return result["body"]


async def apply_edits(
    original: dict,
    candidate: dict,
    evidence: dict,
    operations: list[dict],
    journal_path: Path,
    *,
    tools,
) -> dict:
    reader = NotionBooks(tools, api=tools.call_api)
    identity = review_fingerprint(
        {
            "original": original,
            "candidate": candidate,
            "evidence": evidence,
            "operations": operations,
        }
    )
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())
        if journal["fingerprint"] != identity:
            raise ValueError(
                "Existing journal belongs to different source, evidence or corrections"
            )
    else:
        journal = {
            "version": 1,
            "fingerprint": identity,
            "work_id": evidence["work_id"],
            "pages": {},
            "complete": False,
        }
        write_json(journal_path, journal)

    async def check_outline():
        rows = await reader.outline(
            evidence["discovery"], evidence["extras_source"], view_policy="editorial"
        )
        if outline_identity(rows) != evidence["outline"]:
            raise ValueError("Book order, membership or titles changed since planning")

    await check_outline()
    grouped: dict[str, list[dict]] = {}
    for op in operations:
        grouped.setdefault(op["member"], []).append(op)
    semaphore = asyncio.Semaphore(4)
    stopped = asyncio.Event()

    async def write_page(member: str, selected: list[dict]):
        async with semaphore:
            if stopped.is_set():
                return
            saved = evidence["pages"][member]
            original_blocks = chapters(original)[member]["blocks"]
            if len(saved["native"]) != len(original_blocks):
                raise ValueError("Nested page requires the general manuscript workflow")
            state = journal["pages"].setdefault(
                member, {"expected": saved["native"], "done": 0}
            )
            selected = sorted(
                selected, key=lambda op: (op["index"], op["kind"]), reverse=True
            )

            async def current():
                page = await reader.document(saved["page_id"], page_kind(saved))
                if (
                    page.data_source_id != saved["data_source_id"]
                    or page.properties.get("title") != saved["title"]
                ):
                    raise ValueError(
                        "Page membership/title changed during proofreading"
                    )
                return page.native

            native = await current()
            for n, op in enumerate(selected):
                if stopped.is_set():
                    return
                if n < state["done"]:
                    continue
                block_id = (
                    saved["native"][op["index"]]["id"]
                    if op["kind"] != "append_note"
                    else ""
                )
                after = expected_edit(state["expected"], block_id, op)
                if state.get("pending"):
                    if state["pending"] != after:
                        raise ValueError("Pending mutation differs from saved plan")
                    if native_equal(native, after, new_ids=True):
                        state.update(expected=native, done=n + 1)
                        state.pop("pending")
                        write_json(journal_path, journal)
                        continue
                if not native_equal(native, state["expected"]):
                    raise ValueError(f"Concurrent content edit: {saved['title']}")
                state["pending"] = after
                write_json(journal_path, journal)
                if op["kind"] in {
                    "insert_blank",
                    "append_note",
                    "insert_note",
                    "insert_divider",
                }:
                    blocks = (
                        [{"kind": "divider", "runs": []}]
                        if op["kind"] == "insert_divider"
                        else op["blocks"]
                        if op["kind"] != "insert_blank"
                        else [
                            {"kind": "paragraph", "runs": []}
                            for _ in range(op["count"])
                        ]
                    )
                    payload = {"children": append_payload(blocks)}
                    if block_id:
                        payload["after"] = block_id
                    response = await checked_api(
                        tools,
                        {
                            "method": "PATCH",
                            "path": f"blocks/{saved['page_id']}/children",
                            "json": payload,
                        },
                    )
                    native = acknowledge_append(response, state["expected"], after)
                else:
                    raw = await checked_api(
                        tools, {"method": "GET", "path": f"blocks/{block_id}"}
                    )
                    payload = text_payload(raw, op["before"], op["after"])
                    await checked_api(
                        tools,
                        {
                            "method": "PATCH",
                            "path": f"blocks/{block_id}",
                            "json": payload,
                        },
                    )
                    native = await current()
                if not native_equal(native, after, new_ids=True):
                    raise ValueError(
                        "Notion readback differs; retain the pending journal"
                    )
                state.update(expected=native, done=n + 1)
                state.pop("pending")
                write_json(journal_path, journal)
                # Full readback per bounded group; every response is checked and
                # journaled first. Recovery always starts with a fresh full read.
                if (n + 1) % 10 == 0:
                    native = await current()
                    if not native_equal(native, state["expected"]):
                        raise ValueError("Concurrent edit during proofread batch")
            native = await current()
            if not native_equal(native, state["expected"]):
                raise ValueError("Previously verified content changed")
            state["verified"] = True
            write_json(journal_path, journal)
            print(
                f"Notion verified: {saved['title']} ({len(selected)} edits)", flush=True
            )

    # Collect all worker failures before releasing the credential lock.
    async def guarded(member, selected):
        try:
            await write_page(member, selected)
        except BaseException:
            stopped.set()
            raise

    outcomes = await asyncio.gather(
        *(guarded(m, ops) for m, ops in grouped.items()), return_exceptions=True
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    await check_outline()
    journal["complete"] = True
    write_json(journal_path, journal)
    return {
        "pages_changed": len(grouped),
        "operations": len(operations),
        "verified": True,
        "journal": str(journal_path),
    }
