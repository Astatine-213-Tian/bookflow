"""Extract and prepare EPUB, TXT or agent content JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.runtime.files import digest, write_json
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
    try:
        directory = (
            args.run_dir
            or Path("generated/ingest") / digest(args.source.read_bytes())[:16]
        )
        if args.inventory:
            from src.inputs.epub import inventory_epub

            inventory = inventory_epub(args.source)
            inventory.pop("files")
            inventory["sha256"] = digest(args.source.read_bytes())
            write_json(directory / "inventory.json", inventory)
            print(directory / "inventory.json")
            return 0
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
            print(directory / "quote-candidates.json")
            return 0
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
        print(directory / "source.json")
        return 0
    except (OSError, ValueError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
