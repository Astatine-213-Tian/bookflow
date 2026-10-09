"""Wait for an import's original template request without creating duplicates."""

from __future__ import annotations

from pathlib import Path

from notion_books import NotionBooks

from src.notion.cms import STORAGE, ensure_views


async def recover_template(book: dict, state: Path, config: dict, *, tools) -> None:
    works = config["databases"]["works"]
    if (
        book.get("storage") != STORAGE
        or book.get("catalog_id") != works["data_source_id"]
    ):
        raise ValueError("Template recovery requires a checkpoint for this catalog")
    if book.get("uploaded") or not book.get("work_id"):
        raise ValueError("Template recovery requires an existing, incomplete work")
    reader = NotionBooks(tools, api=tools.call_api)
    page = await reader.page(book["work_id"])
    if page.data_source_id != works["data_source_id"]:
        raise ValueError("Checkpoint work belongs to another catalog")
    # ensure_work already supplied the template during creation, including for
    # legacy checkpoints without template_request. Even a freshly fetched blank
    # page can have that job queued. Reapplying it creates duplicate databases
    # when both jobs eventually finish; recovery must remain read-only.
    await ensure_views(book, state, config, tools=tools)
