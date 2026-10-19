"""Book specs: one maintained config per bilingual book under book_specs/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime.paths import repo_root


def spec_path(book: str | Path) -> Path:
    """Resolve a book slug (``eternal_gate``) or a config path to the spec file."""
    path = Path(book).expanduser()
    if path.is_file():
        return path.resolve()
    candidate = repo_root() / "book_specs" / str(book) / "config.json"
    if candidate.is_file():
        return candidate
    raise ValueError(f"No book spec for {book!r}; expected {candidate}")


def book_slug(config: dict[str, Any]) -> str:
    return Path(config["_config_path"]).parent.name


def load_config(path: str | Path) -> dict[str, Any]:
    resolved = spec_path(path)
    data = json.loads(resolved.read_text(encoding="utf-8"))
    data["_config_path"] = str(resolved)
    return data


def config_path(
    config: dict[str, Any], key: str, default: str | None = None
) -> Path | None:
    raw = config.get(key, default)
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo_root() / path).resolve()
