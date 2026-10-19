"""Extract and prepare EPUB, TXT or agent content JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.output import paths, run_command
from src.runtime.files import digest, write_json
from src.runtime.paths import work_root
from src.workflows.prepare import prepare_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument(
        "--review", type=Path, help="Reviewed EPUB block ranges, omissions and metadata"
    )
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Extract EPUB blocks for agent review without normalizing",
    )
    parser.add_argument("--enrich-metadata", action="store_true")
    parser.add_argument(
        "--quote-review",
        type=Path,
        help="Codex/session decisions for saved quotation candidates",
    )
    parser.add_argument(
        "--scan-quotes",
        action="store_true",
        help="Save quotation candidates for a Codex session without preparing outputs",
    )
    parser.add_argument("--chapter-layout", type=Path)
    parser.add_argument("--chapter-aliases", type=Path)
    parser.add_argument("--official-outline", action="store_true")
    args = parser.parse_args(argv)
    return run_command(lambda: prepare(args))


def prepare(args: argparse.Namespace) -> dict:
    directory = (
        args.run_dir
        or work_root() / "generated" / "ingest" / digest(args.source.read_bytes())[:16]
    )
    if args.inventory:
        from src.inputs.epub import inventory_epub

        inventory = inventory_epub(args.source)
        inventory.pop("files")
        inventory["sha256"] = digest(args.source.read_bytes())
        write_json(directory / "inventory.json", inventory)
        return {"outputs": paths(inventory=directory / "inventory.json")}
    review = json.loads(args.review.read_text()) if args.review else None
    if args.scan_quotes:
        from src.inputs.load import read_input
        from src.content.quote_review import find_quote_candidates

        edition = read_input(
            args.source, title=args.title, author=args.author, review=review
        )
        write_json(
            directory / "quote-candidates.json",
            find_quote_candidates(edition.source, edition.evidence),
        )
        return {
            "outputs": paths(quote_candidates=directory / "quote-candidates.json")
        }
    prepare_file(
        args.source,
        directory,
        title=args.title,
        author=args.author,
        review=review,
        quote_decisions=json.loads(args.quote_review.read_text())
        if args.quote_review
        else None,
        chapter_layout=json.loads(args.chapter_layout.read_text())
        if args.chapter_layout
        else None,
        chapter_aliases=json.loads(args.chapter_aliases.read_text())
        if args.chapter_aliases
        else None,
        use_jjwxc_outline=args.official_outline,
        enrich=args.enrich_metadata,
    )
    return {
        "outputs": paths(
            source=directory / "source.json", report=directory / "report.json"
        )
    }


if __name__ == "__main__":
    raise SystemExit(main())
