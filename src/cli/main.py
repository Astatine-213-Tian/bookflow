"""bookflow: one ``book`` command for every book task.

``book`` alone lists the commands; ``book <command> --help`` shows the arguments
of one. Each command ends with the JSON result line in ``src/cli/output.py``.
"""

from __future__ import annotations

import importlib
import sys

from src.cli.output import emit, log

COMMANDS: dict[str, tuple[str, str]] = {
    "ingest": ("src.cli.ingest", "Find or collect a book; write EPUB, Notion or TXT"),
    "crawl": ("src.cli.crawl", "Collect a source into book JSON for later stages"),
    "prepare": ("src.cli.prepare_book", "Prepare a local EPUB/TXT or agent JSON"),
    "update": ("src.cli.update_book", "Apply an explicit change to local book JSON"),
    "compare": ("src.cli.compare_editions", "Compare two local editions"),
    "proofread": ("src.cli.proofread", "Proofread an edition against Jinjiang"),
    "bilingual": ("src.cli.bilingual", "Make or update a bilingual book from its spec"),
    "dataset": ("src.cli.dataset", "Export TXT and maintain a training dataset"),
    "normalize": ("src.cli.normalize_epub", "Normalize and review an existing EPUB"),
    "enrich-metadata": ("src.cli.enrich_epub_metadata", "Fill missing EPUB metadata"),
    "cover": ("src.cli.cover", "Check, normalize and review 2:3 covers"),
    "notion": ("src.cli.notion_book", "Upload, verify, export or edit Notion drafts"),
    "validate-epub": (
        "src.cli.validate_epub_chapters",
        "Check EPUB chapter numbering and navigation",
    ),
}


def _commands() -> dict[str, str]:
    return {name: summary for name, (_, summary) in COMMANDS.items()}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] in {"-h", "--help"}:
        log("usage: book <command> [arguments]\n")
        for name, summary in _commands().items():
            log(f"  {name:<16} {summary}")
        emit({"status": "complete", "commands": _commands()})
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        message = f"Unknown command {name!r}; run `book` to list commands"
        log(message)
        emit({"status": "failed", "error": message, "commands": _commands()})
        return 1
    # argparse names the program from argv[0], so usage reads `book <command>`.
    sys.argv[0] = f"book {name}"
    return importlib.import_module(COMMANDS[name][0]).main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
