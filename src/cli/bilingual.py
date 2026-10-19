#!/usr/bin/env python3
"""Make a bilingual book from its spec: collect, translate, validate, write.

Progress goes to stderr; the last stdout line is the JSON result described in
``src/cli/output.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.cli.output import run_command
from src.runtime.progress import ProgressLogger, configure_progress
from src.translation.config import book_slug, load_config
from src.translation.methods import METHODS, Baseline, TranslateOptions
from src.workflows.bilingual import (
    build_book,
    translate_snapshot,
    seed_baseline,
    update_book,
    validate_run,
    write_comment_evidence,
)


def _codex_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Codex model in capacity-fallback order; repeat to override the spec",
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument(
        "--overwrite", action="store_true", help="Redo model calls and QA"
    )


def _book_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--book",
        required=True,
        help="Book spec slug under book_specs/ (e.g. eternal_gate) or a config path",
    )


def _options(args: argparse.Namespace, progress: ProgressLogger) -> TranslateOptions:
    return TranslateOptions(
        models=tuple(args.models) if getattr(args, "models", None) else None,
        codex_bin=getattr(args, "codex_bin", "codex"),
        timeout_seconds=getattr(args, "timeout_seconds", None),
        overwrite=getattr(args, "overwrite", False),
        run_codex=not getattr(args, "no_codex", False),
        allow_missing=getattr(args, "allow_missing", False),
        progress=progress,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser(
        "update",
        help="Collect, translate, validate and write one book; resumes a paused run",
    )
    update.add_argument("book", help="Book spec slug or config path")
    update.add_argument(
        "--restart",
        action="store_true",
        help="Start a fresh translation run on the pending snapshot",
    )
    update.add_argument(
        "--recrawl", action="store_true", help="Also collect a fresh snapshot"
    )
    update.add_argument("--headless", action="store_true")
    update.add_argument("-o", "--output", type=Path, help="Override the spec's EPUB")
    _codex_arguments(update)

    seed = sub.add_parser(
        "seed",
        help="Recover a baseline from a bilingual EPUB built earlier for this book",
    )
    seed.add_argument("book", help="Book spec slug or config path")
    seed.add_argument("--from-epub", type=Path, required=True)
    seed.add_argument(
        "--replace", action="store_true", help="Replace an existing baseline"
    )
    seed.add_argument("--headless", action="store_true")

    translate = sub.add_parser(
        "translate", help="Translate a snapshot with the spec's method"
    )
    translate.add_argument("snapshot", type=Path)
    _book_argument(translate)
    translate.add_argument("--run-dir", type=Path, required=True)
    translate.add_argument("--baseline-snapshot", type=Path)
    translate.add_argument("--baseline-run", type=Path)
    translate.add_argument(
        "--no-codex",
        action="store_true",
        help="Prepare requests only (neutral methods); outputs are written later",
    )
    _codex_arguments(translate)

    validate = sub.add_parser(
        "validate", help="Run the method's validation and review gates"
    )
    validate.add_argument("run_dir", type=Path)
    _book_argument(validate)
    validate.add_argument("--snapshot", type=Path)
    validate.add_argument(
        "--allow-missing",
        action="store_true",
        help="Neutral methods: accept paragraphs still untranslated after retry",
    )
    _codex_arguments(validate)

    build = sub.add_parser("build", help="Write the bilingual book from a valid run")
    build.add_argument("snapshot", type=Path)
    _book_argument(build)
    build.add_argument("--run-dir", type=Path, required=True)
    build.add_argument("-o", "--output", type=Path, help="Override the spec's EPUB")
    build.add_argument("--allow-missing", action="store_true")

    comments = sub.add_parser(
        "comment-evidence",
        help="Extract authoritative reply threads for glossary review",
    )
    comments.add_argument("snapshot", type=Path)
    _book_argument(comments)
    comments.add_argument("--output", type=Path)

    sub.add_parser("methods", help="List registered translation methods")
    return parser


def run(args: argparse.Namespace, progress: ProgressLogger) -> dict[str, Any]:
    if args.command == "methods":
        return {
            "status": "complete",
            "methods": {name: m.description for name, m in METHODS.items()},
        }
    options = _options(args, progress)
    if args.command == "update":
        return update_book(
            args.book,
            restart=args.restart,
            recrawl=args.recrawl,
            headless=args.headless,
            output=args.output,
            options=options,
        )
    if args.command == "seed":
        return seed_baseline(
            args.book,
            args.from_epub,
            replace=args.replace,
            headless=args.headless,
            progress=progress,
        )
    config = load_config(args.book)
    base = {"status": "complete", "book": book_slug(config)}
    if args.command == "translate":
        if (args.baseline_snapshot is None) != (args.baseline_run is None):
            raise ValueError("Pass both --baseline-snapshot and --baseline-run")
        baseline = (
            Baseline(args.baseline_snapshot, args.baseline_run)
            if args.baseline_snapshot
            else None
        )
        translate_snapshot(
            args.snapshot, args.run_dir, config, baseline=baseline, options=options
        )
        return {**base, "run": str(args.run_dir)}
    if args.command == "validate":
        summary = validate_run(
            args.run_dir, config, snapshot_dir=args.snapshot, options=options
        )
        return {
            **base,
            "run": str(args.run_dir),
            "glossary_candidates": summary.get("glossary_candidate_count"),
        }
    if args.command == "build":
        written = build_book(
            args.snapshot,
            args.run_dir,
            config,
            output=args.output,
            options=options,
        )
        check = written.epub_check
        return {
            **base,
            "outputs": {
                "epub": str(written.epub_path) if written.epub_path else None,
                "txt": str(written.txt_path) if written.txt_path else None,
            },
            "epub_check": list(check.issues) if check else None,
        }
    if args.command == "comment-evidence":
        evidence = write_comment_evidence(args.snapshot, config, args.output)
        return {
            **base,
            "comment_evidence": evidence["path"],
            "threads": evidence["thread_count"],
            "authoritative_replies": evidence["authoritative_reply_count"],
        }
    raise ValueError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_progress(debug=args.verbose)
    progress = ProgressLogger()
    resume = f"book bilingual update {args.book}" if args.command == "update" else None
    return run_command(lambda: run(args, progress), resume=resume)


if __name__ == "__main__":
    raise SystemExit(main())
