"""Collect a known source into the shared book JSON, with optional source evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cli.output import paths, run_command
from src.crawler.registry import PARSERS
from src.workflows.collect import collect_source, crawl_options


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?")
    parser.add_argument(
        "--config",
        type=Path,
        help="Book spec containing source.provider, source.url and source.language",
    )
    parser.add_argument("--provider", choices=[p.name for p in PARSERS])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--language", default="")
    parser.add_argument(
        "--comments",
        action="store_true",
        help="Fetch required comment evidence where supported",
    )
    parser.add_argument("--extra-post-id", action="append", default=[])
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    return run_command(lambda: collect(args))


def collect(args: argparse.Namespace) -> dict:
    config = json.loads(args.config.read_text()) if args.config else {}
    source = config.get("source", {})
    target = args.target or source.get("url")
    if not target:
        raise ValueError("Provide a target URL or --config with source.url")
    options = crawl_options(
        config,
        delay=args.delay,
        concurrency=args.concurrency,
        headless=args.headless,
        title=args.title,
        author=args.author,
        language=args.language,
        include_comments=args.comments,
        extra_post_ids=tuple(args.extra_post_id),
    )
    path = collect_source(
        target,
        args.output,
        provider=args.provider or source.get("provider"),
        options=options,
    )
    return {"outputs": paths(source=path, evidence=path.parent / "evidence.json")}


if __name__ == "__main__":
    raise SystemExit(main())
