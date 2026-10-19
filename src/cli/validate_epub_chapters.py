"""Validate EPUB chapter numbering and navigation."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.output import log, run_command
from src.epub.validate import validate_epub
from src.runtime.paths import work_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[work_root() / "books"],
        help="EPUB files or directories containing EPUB files",
    )
    args = parser.parse_args(argv)
    return run_command(lambda: validate(args.paths))


def validate(targets: list[Path]) -> dict:
    epub_paths: list[Path] = []
    for path in targets:
        if path.is_dir():
            epub_paths.extend(sorted(path.glob("*.epub")))
        else:
            epub_paths.append(path)
    if not epub_paths:
        raise ValueError("No EPUB files found")

    books = {}
    for path in epub_paths:
        issues, chapter_count = validate_epub(path)
        log(
            f"{'FAIL' if issues else 'OK  '} {path} "
            f"({chapter_count} numbered chapter entries)"
        )
        for issue in issues:
            log(f"  - {issue}")
        books[str(path)] = {"chapters": chapter_count, "issues": issues}
    failed = sum(1 for book in books.values() if book["issues"])
    return {
        "status": "issues_found" if failed else "complete",
        "checked": len(books),
        "with_issues": failed,
        "books": books,
    }

if __name__ == "__main__":
    raise SystemExit(main())
