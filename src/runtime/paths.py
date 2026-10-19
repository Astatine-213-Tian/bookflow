from __future__ import annotations

import os
import re
from pathlib import Path

INVALID_PATH_CHARS_RE = re.compile(r'[\\/:*?"<>|\0]+')
SPACE_RE = re.compile(r"\s+")


def safe_path_name(value: str, fallback: str) -> str:
    cleaned = INVALID_PATH_CHARS_RE.sub("_", value or "")
    cleaned = SPACE_RE.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


WORK_ROOT_ENV = "BOOKFLOW_WORK_ROOT"


def repo_root() -> Path:
    """The checkout: code, book specs, docs, assets and research."""
    return Path(__file__).resolve().parents[2]


def work_root() -> Path:
    """Where working data lives (books/, generated/, state/, bilingual/).

    The checkout, whatever the current directory, unless BOOKFLOW_WORK_ROOT is set.
    """
    raw = os.environ.get(WORK_ROOT_ENV)
    return Path(raw).expanduser().resolve() if raw else repo_root()


def default_output_path(title: str, author: str = "", *, suffix: str = ".epub") -> Path:
    out_dir = work_root() / "books"
    if author.strip():
        out_dir = out_dir / safe_path_name(author, "Unknown Author")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{safe_path_name(title, 'book')}{suffix}"


def resolve_output_path(
    output: str | Path | None, title: str, author: str = ""
) -> Path:
    out_path = Path(output) if output else default_output_path(title, author)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def default_txt_output_path(title: str, author: str = "") -> Path:
    return default_output_path(title, author, suffix=".txt")


def resolve_txt_output_path(
    output: str | Path | None, title: str, author: str = ""
) -> Path:
    out_path = Path(output) if output else default_txt_output_path(title, author)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def dataset_txt_output_path(
    root: str | Path,
    *,
    title: str,
    author: str,
    time_area: str,
    genre: str,
) -> Path:
    # Keep classification metadata in the manifest; keep files easy to scan by author.
    _ = (time_area, genre)
    root_path = Path(root)
    raw_root = root_path if root_path.name == "raw" else root_path / "raw"
    out_path = (
        raw_root
        / safe_path_name(author, "Unknown Author")
        / f"{safe_path_name(title, 'book')}.txt"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path
