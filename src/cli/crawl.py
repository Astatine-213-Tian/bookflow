"""Collect a known source into the shared book JSON, with optional source evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.crawler.models import CrawlOptions
from src.crawler.registry import PARSERS
from src.workflows.collect import collect_source


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
    try:
        config = json.loads(args.config.read_text()) if args.config else {}
        source = config.get("source", {})
        target = args.target or source.get("url")
        if not target:
            raise ValueError("Provide a target URL or --config with source.url")
        options = CrawlOptions(
            delay=args.delay,
            concurrency=max(1, args.concurrency),
            headless=args.headless,
            title=args.title or config.get("title", ""),
            author=args.author or config.get("author", ""),
            language=args.language or source.get("language", ""),
            include_comments=args.comments or source.get("comments", False),
            extra_post_ids=tuple(
                args.extra_post_id or source.get("extra_post_ids", [])
            ),
        )
        path = collect_source(
            target,
            args.output,
            provider=args.provider or source.get("provider"),
            options=options,
        )
        print(path)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
