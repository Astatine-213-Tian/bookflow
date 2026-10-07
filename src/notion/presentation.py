"""Import-owned volume colors and public cover orchestration over MCP."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from notion_books import FIELDS, NotionBooks

from src.notion.cms import chapter_entries
from src.notion.cover import validate_cover
from src.notion.mcp import finish_write
from src.runtime.files import digest, write_json

VOLUME_COLORS = (
    "blue",
    "green",
    "purple",
    "orange",
    "pink",
    "red",
    "yellow",
    "brown",
    "gray",
)


async def volume_options(book: dict, *, tools) -> dict:
    schema = await NotionBooks(tools).catalog(
        {
            "chapters": {
                "data_source_id": book["chapters_data_source_id"],
                "view_id": book["chapters_view_id"],
                "fields": {
                    FIELDS["parent_title"]: {"type": "select", "writable": True}
                },
            }
        }
    )
    options = (
        schema["chapters"]["properties"][FIELDS["parent_title"]].get("options") or []
    )
    return {o["name"]: o.get("color", "default") for o in options}


async def ensure_volume_colors(book: dict, state: Path, *, tools) -> None:
    names = list(dict.fromkeys(parent for _, parent in chapter_entries(book) if parent))
    if not names:
        return
    existing = await volume_options(book, tools=tools)
    expected = book.get("volume_colors")
    if expected is None:
        expected = {name: existing[name] for name in names if name in existing}
        for name in names:
            if name not in expected:
                available = [c for c in VOLUME_COLORS if c not in expected.values()]
                expected[name] = (
                    available[0]
                    if available
                    else VOLUME_COLORS[len(expected) % len(VOLUME_COLORS)]
                )
        book["volume_colors"] = expected
        write_json(state, book)
    missing = {name: color for name, color in expected.items() if name not in existing}
    if missing:
        values = existing | missing
        sql = (
            'ALTER COLUMN "'
            + FIELDS["parent_title"].replace('"', '""')
            + '" SET SELECT('
        )
        sql += (
            ", ".join(
                "'" + name.replace("'", "''") + "':" + color
                for name, color in values.items()
            )
            + ")"
        )
        # Schema editing is an import presentation decision. Chapter CRUD and
        # schema inspection remain in notion-books.
        await tools.call(
            "notion-update-data-source",
            {"data_source_id": book["chapters_data_source_id"], "statements": sql},
        )
    actual = await volume_options(book, tools=tools)
    if any(actual.get(name) != color for name, color in (existing | expected).items()):
        raise ValueError(
            "Volume color readback differs; reconcile without replacing existing options"
        )


def public_cover(url: str) -> bytes:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Cover requires a public HTTP(S) URL")
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    validate_cover(response.content)
    return response.content


async def attach_public_cover(book: dict, state: Path, *, tools) -> None:
    if book.get("cover_uploaded"):
        return
    url = book["cover_url"]
    reader = NotionBooks(tools, api=tools.call_api)
    page = await reader.page(book["work_id"])
    if not page.cover_known:
        raise ValueError("Notion omitted cover metadata")
    if page.cover is not None and page.cover.get("url") != url:
        raise ValueError(
            "Book already has a different cover; preserve it and reconcile"
        )
    if page.cover is None:
        if book.get("cover_pending"):
            raise ValueError("Cover write is uncertain; inspect before retrying")
        book["cover_pending"] = url
        write_json(state, book)
        await finish_write(
            tools,
            "notion-update-page",
            {
                "page_id": book["work_id"],
                "command": "update_properties",
                "properties": {},
                "cover": url,
            },
        )
    page = await reader.page(book["work_id"])
    if not page.cover_known or not page.cover or page.cover.get("url") != url:
        raise ValueError("External cover readback differs")
    if digest(await asyncio.to_thread(public_cover, url)) != book["cover_sha256"]:
        raise ValueError("Public cover bytes changed since preparation")
    book.pop("cover_pending", None)
    book["cover_uploaded"] = True
    write_json(state, book)
