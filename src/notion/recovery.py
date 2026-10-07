"""Explicit, checkpointed recovery of an empty book template through MCP."""

from __future__ import annotations

from pathlib import Path

from notion_books import CATALOG_SCHEMA, NotionBooks, notion_id

from src.notion.cms import STORAGE, ensure_views
from src.notion.mcp import finish_write
from src.runtime.files import write_json


async def recover_template(book: dict, state: Path, config: dict, *, tools) -> None:
    works = config["databases"]["works"]
    if (
        book.get("storage") != STORAGE
        or book.get("catalog_id") != works["data_source_id"]
    ):
        raise ValueError("Template recovery requires a checkpoint for this catalog")
    if book.get("uploaded") or not book.get("work_id"):
        raise ValueError("Template recovery requires an existing, incomplete work")
    reader = NotionBooks(tools)
    page = await reader.page(book["work_id"])
    if page.data_source_id != works["data_source_id"]:
        raise ValueError("Checkpoint work belongs to another catalog")
    if book.get("template_recovery_requested") or page.shell.strip():
        # An accepted or uncertain append must never be repeated.
        await ensure_views(book, state, config, tools=tools)
        return
    if any(i.get("page_id") for i in [*book["chapters"].values(), *book["extras"]]):
        raise ValueError("Template recovery cannot replace existing chapter content")
    catalog = await reader.catalog(
        {
            "works": works
            | {
                "fields": {
                    name: {"type": kind, "writable": True}
                    for name, kind in CATALOG_SCHEMA["works"].items()
                }
            }
        }
    )
    template = catalog["works"].get("default_template")
    if not template:
        raise ValueError("Works has no default template")
    book["template_recovery_requested"] = notion_id(template)
    write_json(state, book)
    await finish_write(
        tools,
        "notion-update-page",
        {
            "page_id": book["work_id"],
            "command": "apply_template",
            "template_id": notion_id(template),
        },
    )
    await ensure_views(book, state, config, tools=tools)
