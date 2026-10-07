"""Upload and independently verify native CMS covers."""

from __future__ import annotations

import io
import os
import warnings
from pathlib import Path

import httpx
from notion_books import API_VERSION, NotionBooks
from PIL import Image

from src.runtime.files import digest, write_json
from src.notion.api import api_request, api_token

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000


def validate_cover(data: bytes) -> str:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("CMS cover must be nonempty and at most 10 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ValueError("CMS cover must be PNG or JPEG")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("CMS cover must be at most 25 million pixels")
                suffix = "png" if image.format == "PNG" else "jpg"
                image.verify()
        return suffix
    except (
        OSError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as error:
        raise ValueError("Invalid CMS cover image") from error


async def upload_cover(book: dict, state: Path, *, tools) -> None:
    if book.get("cover_uploaded"):
        return
    data = Path(book["cover_asset"]).read_bytes()
    if digest(data) != book["cover_sha256"]:
        raise ValueError("Cover asset changed since preparation")
    suffix = validate_cover(data)
    token = api_token()
    reader = NotionBooks(tools)
    page = await reader.page(book["work_id"])
    if not page.cover_known:
        raise ValueError("Notion did not provide page cover metadata")
    existing_cover = page.cover
    if book.get("cover_pending"):
        # Never overwrite a later manual cover after an uncertain PATCH response.
        raise ValueError(
            "Cover attachment result is uncertain; inspect the page and reconcile cover_pending before retrying"
        )
    if existing_cover is not None:
        raise ValueError(
            "Book already has a cover; reconcile it before uploading the crawler cover"
        )
    async with httpx.AsyncClient(
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": API_VERSION,
        },
        timeout=60,
        follow_redirects=False,
    ) as client:
        api = NotionBooks(api=lambda request: api_request(client, request))
        await api.check_page_access(book["work_id"])
        id = await api.upload_cover(suffix, data)
        book["cover_pending"] = id
        write_json(state, book)
        await api.attach_cover(book["work_id"], id)
    await verify_cover(book, state, tools=tools)


async def verify_cover(book: dict, state: Path, *, tools) -> None:
    """Verify a browser/API upload against prepared bytes before completing it."""
    if not book.get("cover_asset") or not book.get("cover_sha256"):
        raise ValueError("Checkpoint has no prepared native cover")
    if digest(Path(book["cover_asset"]).read_bytes()) != book["cover_sha256"]:
        raise ValueError("Cover asset changed since preparation")
    reader = NotionBooks(tools)
    page = await reader.page(book["work_id"])
    if not page.cover_known:
        raise ValueError("Notion did not provide page cover metadata")
    cover = page.cover
    if cover is None or cover["kind"] != "file":
        raise ValueError("CMS cover readback is not a native uploaded file")
    # Only download the newly attached native file; never persist its signed URL.
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        response = await client.get(cover["url"])
        if not response.is_success or digest(response.content) != book["cover_sha256"]:
            raise ValueError("CMS uploaded cover bytes differ from the prepared cover")
    book.pop("cover_pending", None)
    book.pop("cover_browser_task", None)
    book["cover_uploaded"] = True
    write_json(state, book)


async def finish_cover(book: dict, state: Path, *, tools) -> None:
    if book.get("cover_uploaded"):
        return
    if book.get("cover_asset"):
        data = Path(book["cover_asset"]).read_bytes()
        validate_cover(data)
        if digest(data) != book["cover_sha256"]:
            raise ValueError("Cover asset changed since preparation")
        if os.environ.get("NOTION_API_TOKEN", "").strip():
            await upload_cover(book, state, tools=tools)
            return
        task = state.parent / "cover-browser.json"
        write_json(
            task,
            {
                "work_id": book["work_id"],
                "url": "https://www.notion.so/" + book["work_id"],
                "asset": str(Path(book["cover_asset"]).resolve()),
                "sha256": book["cover_sha256"],
                "state": str(state.resolve()),
                "procedure": ".agents/skills/book-management/references/notion-cover.md",
            },
        )
        book["cover_browser_task"] = str(task)
        write_json(state, book)
        raise ValueError(
            f"Content uploaded; native cover awaits browser upload. Follow .agents/skills/book-management/references/notion-cover.md using {task}, then book-notion verify-cover --state {state}"
        )
    elif book.get("cover_url"):
        from src.notion.presentation import attach_public_cover

        await attach_public_cover(book, state, tools=tools)
