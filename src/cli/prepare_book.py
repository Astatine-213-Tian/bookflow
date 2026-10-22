"""Extract and prepare EPUB, TXT or agent content JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.output import paths, run_command
from src.metadata.enrich import ENRICH_FIELDS, parse_enrich_fields
from src.workflows.prepare import (
    default_run_dir,
    prepare_file,
    write_inventory,
    write_quote_candidates,
)


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
    parser.add_argument(
        "--enrich",
        metavar="FIELDS",
        help="Replace metadata with Jinjiang/KadoKado values: all, or a comma-separated "
        "subset of " + ",".join(ENRICH_FIELDS) + "; volumes applies the official volume titles",
    )
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
    args = parser.parse_args(argv)
    try:
        args.enrich = parse_enrich_fields(args.enrich) if args.enrich else frozenset()
    except ValueError as error:
        parser.error(str(error))
    return run_command(lambda: prepare(args))


def prepare(args: argparse.Namespace) -> dict:
    directory = args.run_dir or default_run_dir(args.source)
    if args.inventory:
        return {"outputs": paths(inventory=write_inventory(args.source, directory))}
    review = json.loads(args.review.read_text()) if args.review else None
    if args.scan_quotes:
        candidates = write_quote_candidates(
            args.source, directory, title=args.title, author=args.author, review=review
        )
        return {"outputs": paths(quote_candidates=candidates)}
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
        enrich=args.enrich,
    )
    return {
        "outputs": paths(
            source=directory / "source.json", report=directory / "report.json"
        )
    }


if __name__ == "__main__":
    raise SystemExit(main())
