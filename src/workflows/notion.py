"""Notion destination tasks.

Each task that touches an import checkpoint holds its lock and one MCP session,
so a checkpoint has one writer whichever entry point starts the task.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Any

from src.notion.cms import CONFIG
from src.notion.mcp import AUTH_FILE, TokenStore, connect, exclusive_lock
from src.runtime.files import write_json


@asynccontextmanager
async def _session(state: Path | None = None):
    """The checkpoint lock (when there is a checkpoint), then one MCP session."""
    lock = exclusive_lock(state.parent / "import.lock") if state else nullcontext()
    with lock:
        store = TokenStore(AUTH_FILE)
        with store.locked():
            async with connect(store) as tools:
                yield tools


def _require_token() -> None:
    from src.notion.api import api_token

    api_token()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


# ------------------------------------------------------------------------------
# Upload and recovery
# ------------------------------------------------------------------------------


def upload(
    source_path: Path,
    *,
    cover: Path | None = None,
    cover_url: str | None = None,
    keep_original_cover: bool = False,
    config_path: Path = CONFIG,
) -> Path:
    """Upload a prepared source as a draft; returns its import checkpoint."""
    from src.content.prepared import load_prepared_source
    from src.notion.upload import upload_source
    from src.workflows.cover import deliver_cover

    source, prepared_cover, prepared_mime = load_prepared_source(source_path)
    cover_bytes = None
    if not cover_url:
        cover_bytes, _, _ = deliver_cover(
            prepared_cover,
            prepared_mime or "image/jpeg",
            source_path.parent,
            source=source_path,
            replacement=cover,
            keep_original=keep_original_cover,
        )
    return upload_source(
        source, cover_bytes=cover_bytes, cover_url=cover_url, config_path=config_path
    )


def resume(state: Path, config_path: Path = CONFIG) -> dict[str, Any]:
    from src.notion.upload import upload_draft

    _require_token()
    config = _read(config_path)

    async def run() -> dict[str, Any]:
        async with _session(state) as tools:
            book = _read(state)
            await upload_draft(book, state, config, tools=tools)
            return {"notion_url": "https://www.notion.so/" + book["work_id"]}

    return asyncio.run(run())


def verify(
    state: Path, config_path: Path = CONFIG, report: Path | None = None
) -> dict[str, Any]:
    from src.notion.verification import verify_draft

    _require_token()
    config = _read(config_path)

    async def run() -> dict[str, Any]:
        async with _session(state) as tools:
            return await verify_draft(_read(state), config, tools=tools)

    result = asyncio.run(run())
    if report:
        write_json(report, result)
    return result


def verify_cover(state: Path) -> None:
    from src.notion.cover import verify_cover as verify_native_cover

    async def run() -> None:
        async with _session(state) as tools:
            await verify_native_cover(_read(state), state, tools=tools)

    asyncio.run(run())


def recover_template(state: Path, config_path: Path = CONFIG) -> None:
    from src.notion.recovery import recover_template as recover

    config = _read(config_path)

    async def run() -> None:
        async with _session(state) as tools:
            await recover(_read(state), state, config, tools=tools)

    asyncio.run(run())


def resolve_shared_extra(state: Path, extra: int, use_existing: str | None) -> None:
    """Record the reviewed decision for one possibly duplicated shared extra."""
    from src.notion.duplicates import resolve_extra

    with exclusive_lock(state.parent / "import.lock"):
        resolve_extra(state, extra, use_existing=use_existing)


# ------------------------------------------------------------------------------
# Read and edit current content
# ------------------------------------------------------------------------------


def export(state: Path) -> dict[str, Any]:
    """Read the current editor content of an uploaded book."""
    from src.notion.update import read_current

    _require_token()

    async def run() -> dict[str, Any]:
        async with _session(state) as tools:
            return await read_current(_read(state), tools=tools)

    return asyncio.run(run())


def update(
    state: Path, change_path: Path, config_path: Path = CONFIG
) -> dict[str, Any]:
    """Apply an explicit change to the uploaded book and read it back."""
    from src.notion.update import apply_update

    _require_token()
    change, config = _read(change_path), _read(config_path)

    async def run() -> dict[str, Any]:
        async with _session(state) as tools:
            return await apply_update(state, change, config, tools=tools)

    return asyncio.run(run())


# ------------------------------------------------------------------------------
# Local MCP tokens
# ------------------------------------------------------------------------------


def login() -> None:
    from src.notion.mcp import login as authorize

    store = TokenStore(AUTH_FILE)
    with store.locked():
        asyncio.run(authorize(store))


def logout() -> None:
    store = TokenStore(AUTH_FILE)
    with store.locked():
        store.clear_tokens()
