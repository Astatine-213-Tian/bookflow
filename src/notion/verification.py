"""Fresh readback of an import checkpoint; never modify editorial content."""

from __future__ import annotations

import asyncio
import json

from notion_books import FIELDS, NotionBooks, from_markdown, relation_ids

from src.notion.cms import AUTHOR_HOMEPAGE, chapter_entries
from src.notion.duplicates import fingerprint
from src.notion.presentation import public_cover, volume_options
from src.runtime.files import digest


def _value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


async def verify_draft(book: dict, config: dict, *, tools) -> dict:
    reader = NotionBooks(tools)
    page = await reader.page(book["work_id"])
    if page.data_source_id != config["databases"]["works"]["data_source_id"]:
        raise ValueError("Book belongs to another catalog")
    metadata = book["metadata"]
    for key in ("title", "description", "source", "language", "series"):
        expected = metadata.get(key) or ("zh-CN" if key == "language" else "")
        actual = page.properties.get(FIELDS[key]) or ""
        if key == "description":
            actual = actual.replace("<br>", "\n")
        if actual != expected:
            raise ValueError(f"Notion metadata differs: {key}")
    if (_value(page.properties.get(FIELDS["subjects"])) or []) != (
        metadata.get("subjects") or []
    ):
        raise ValueError("Notion subjects differ")
    if metadata.get("date") and metadata["date"][:10] != page.properties.get(
        "date:" + FIELDS["date"] + ":start"
    ):
        raise ValueError("Notion publication date differs")
    if metadata.get("series_position") and float(metadata["series_position"]) != float(
        page.properties.get(FIELDS["series_position"], 0)
    ):
        raise ValueError("Notion series position differs")
    authors = []
    for id in relation_ids(page.properties.get(FIELDS["authors"])):
        author = await reader.page(id)
        name = author.properties[FIELDS["authors"]]
        authors.append(name)
        if homepage := book.get("author_jjwxc_urls", {}).get(name):
            if author.properties.get(AUTHOR_HOMEPAGE) != homepage:
                raise ValueError("Author Jinjiang homepage differs")
    if authors != (metadata.get("creators") or [metadata["creator"]]):
        raise ValueError("Notion author relations differ")
    entries = chapter_entries(book)
    rows = await reader.rows(book["chapters_view_id"])
    extras = await reader.rows(book["view_id"])
    if [r["id"] for r in rows] != [book["chapters"][m]["page_id"] for m, _ in entries]:
        raise ValueError("Chapter manual order differs")
    if [r["id"] for r in extras] != [e["page_id"] for e in book["extras"]]:
        raise ValueError("Extra manual order differs")
    checked = 0
    for item, parent, title_field in [
        *[
            (book["chapters"][member], parent, FIELDS["chapter_title"])
            for member, parent in entries
        ],
        *[(extra, None, FIELDS["extra_title"]) for extra in book["extras"]],
    ]:
        document = await reader.document(item["page_id"])
        expected = item.get("reuse_fingerprint") or fingerprint(
            item["title"], item["blocks"]
        )
        if (
            fingerprint(
                document.properties.get(title_field), from_markdown(document.markdown)
            )
            != expected
        ):
            raise ValueError(f"Content readback differs: {item['title']}")
        if (
            parent is not None
            and (document.properties.get(FIELDS["parent_title"]) or "") != parent
        ):
            raise ValueError(f"Parent title differs: {item['title']}")
        if parent is None and book["work_id"] not in relation_ids(
            document.properties.get(FIELDS["related_works"])
        ):
            raise ValueError(f"Extra relation differs: {item['title']}")
        checked += 1
        if checked % 20 == 0:
            print(
                f"Verified full content: {checked}/{len(entries) + len(extras)}",
                flush=True,
            )
    if book.get("volume_colors"):
        actual = await volume_options(book, tools=tools)
        if any(
            actual.get(name) != color for name, color in book["volume_colors"].items()
        ):
            raise ValueError("Volume colors differ from the import checkpoint")
    if (book.get("cover_asset") or book.get("cover_url")) and not book.get(
        "cover_uploaded"
    ):
        raise ValueError("Prepared cover has not been uploaded and verified")
    if book.get("cover_uploaded"):
        if not page.cover_known or not page.cover:
            raise ValueError("Imported cover is missing")
        if book.get("cover_url") and page.cover.get("url") != book["cover_url"]:
            raise ValueError("Public cover URL differs")
        if book.get("cover_sha256"):
            data = await asyncio.to_thread(public_cover, page.cover["url"])
            if digest(data) != book["cover_sha256"]:
                raise ValueError("Imported cover bytes differ")
    return {
        "notion_url": "https://www.notion.so/" + book["work_id"],
        "chapters": len(entries),
        "extras": len(extras),
        "full_content_readbacks": checked,
        "metadata_verified": True,
        "order_verified": True,
        "volume_colors": book.get("volume_colors", {}),
        "cover": {
            "present": bool(page.cover),
            "kind": page.cover.get("kind") if page.cover else None,
        },
    }
