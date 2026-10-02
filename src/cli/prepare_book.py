"""Prepare a supplied local EPUB/TXT for the shared outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.runtime.files import digest
from src.workflows.local import prepare_local


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    parser.add_argument(
        "--chapter-aliases",
        type=Path,
        help="Reviewed JSON map: local complete chapter title -> official title",
    )
    parser.add_argument(
        "--keep-outline",
        action="store_true",
        help="Explicitly preserve the edition outline instead of applying Jinjiang's directory",
    )
    args = parser.parse_args(argv)
    try:
        run_dir = (
            args.run_dir
            or Path("generated/local_imports") / digest(args.source.read_bytes())[:16]
        )
        aliases = (
            json.loads(args.chapter_aliases.read_text())
            if args.chapter_aliases
            else None
        )
        prepare_local(
            args.source,
            run_dir,
            title=args.title,
            author=args.author,
            chapter_aliases=aliases,
            use_jjwxc_outline=not args.keep_outline,
        )
        print(f"Prepared source: {run_dir / 'source.json'}")
        return 0
    except (OSError, ValueError) as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
