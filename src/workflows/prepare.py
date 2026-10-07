"""Shared preparation of already-extracted content for every destination."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Callable

from src.content.contract import metadata_defaults, override_metadata, validate_book
from src.content.edition_outline import apply_edition_layout, apply_jjwxc_outline
from src.content.normalize import normalize_book
from src.metadata.enrich import enrich_source


def prepare_book(
    source: dict,
    *,
    enrich: bool = False,
    overrides: dict | None = None,
    layout: dict | None = None,
    aliases: dict | None = None,
    official_outline: bool = False,
) -> tuple[dict, dict]:
    book = copy.deepcopy(source)
    book["metadata"] = override_metadata(
        metadata_defaults(book["metadata"]), overrides or {}
    )
    reports = {}
    if layout is not None:
        reports["layout"] = apply_edition_layout(book, layout)
    if enrich:
        reports["metadata"] = enrich_source(book)
        if official_outline and reports["metadata"].get("table_of_contents"):
            reports["outline"] = apply_jjwxc_outline(
                book, reports["metadata"]["table_of_contents"], aliases=aliases
            )
    if re.fullmatch(r"[0-9]{4}", book["metadata"].get("date", "")):
        book["metadata"]["date"] += "-01-01"
    from src.content.references import canonicalize_footnotes

    book["chapters"] = {
        k: canonicalize_footnotes(ch) for k, ch in book["chapters"].items()
    }
    book["extras"] = [canonicalize_footnotes(ch) for ch in book["extras"]]
    validate_book(book)
    book, reports["normalization"] = normalize_book(book)
    validate_book(book)
    return book, reports


def save_prepared(
    book: dict,
    run_dir: Path,
    reports: dict,
    cover: bytes | None = None,
    mime: str = "image/jpeg",
    *,
    evidence: dict | None = None,
) -> Path:
    """Persist the shared result together with its review findings and evidence."""
    from src.content.prepared import save_source
    from src.runtime.files import write_json

    source_path = run_dir / "source.json"
    write_json(run_dir / "report.json", reports)
    if evidence is not None:
        write_json(run_dir / "evidence.json", evidence)
    save_source(book, source_path, cover, mime)
    return source_path


def preparation_fingerprint() -> str:
    """Invalidate prepared results when content rules or their implementation change."""
    from src.content.contract import SCHEMA_PATH
    from src.runtime.files import digest

    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "docs/normalization.md",
        SCHEMA_PATH,
        *sorted((root / "src/content").glob("*.py")),
        *sorted((root / "src/inputs").glob("*.py")),
        *sorted((root / "src/metadata").glob("*.py")),
        Path(__file__),
        Path(__file__).with_name("quote_review.py"),
        root / "src/runtime/codex_review.py",
    ]
    return digest(b"".join(path.read_bytes() for path in paths))


def prepare_file(
    path: Path,
    run_dir: Path,
    *,
    title: str = "",
    author: str = "",
    review: dict | None = None,
    chapter_aliases: dict | None = None,
    chapter_layout: dict | None = None,
    use_jjwxc_outline: bool = False,
    enrich: bool = False,
    quote_decisions: dict | None = None,
    quote_runner: Callable[[str], str] | None = None,
) -> tuple[dict, bytes | None, str]:
    import json
    from pathlib import Path

    from src.content.prepared import load_prepared_source
    from src.inputs.load import read_input
    from src.runtime.files import digest, write_json

    path, run_dir = Path(path), Path(run_dir)
    if path.resolve() == (run_dir / "source.json").resolve():
        raise ValueError("Use a fresh run directory; input is preserved")
    if path.suffix.lower() == ".json":
        load_prepared_source(
            path
        )  # Verify source assets even when a prepared cache exists.
    signature = {
        "input": digest(path.read_bytes()),
        "rules": preparation_fingerprint(),
        "title": title,
        "author": author,
        "review": review,
        "layout": chapter_layout,
        "aliases": chapter_aliases,
        "enrich": enrich,
        "official_outline": use_jjwxc_outline,
        "quote_decisions": quote_decisions,
    }
    manifest = run_dir / "input.json"
    source_path = run_dir / "source.json"
    if source_path.exists():
        if not manifest.exists() or json.loads(manifest.read_text()) != signature:
            raise ValueError("Preparation inputs changed; use a fresh --run-dir")
        return load_prepared_source(source_path)
    edition = read_input(path, title=title, author=author, review=review)
    from src.workflows.quote_review import review_quotes

    reviewed, quote_report = review_quotes(
        edition.source,
        edition.evidence,
        run_dir,
        decisions=quote_decisions,
        runner=quote_runner,
    )
    overrides = {k: v for k, v in [("title", title), ("creator", author)] if v}
    book, reports = prepare_book(
        reviewed,
        enrich=enrich,
        overrides=overrides,
        layout=chapter_layout,
        aliases=chapter_aliases,
        official_outline=use_jjwxc_outline,
    )
    if digest(path.read_bytes()) != signature["input"]:
        raise ValueError("Source changed during preparation")
    run_dir.mkdir(parents=True, exist_ok=True)
    reports["quote_review"] = quote_report
    write_json(manifest, signature)
    save_prepared(
        book,
        run_dir,
        reports,
        edition.cover,
        edition.cover_mime,
        evidence=edition.evidence,
    )
    return book, edition.cover, edition.cover_mime
