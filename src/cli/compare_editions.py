"""Compare two explicitly supplied local editions and report text differences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.runtime.files import write_json
from src.workflows.edition_comparison import compare_editions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--author", default="")
    args = parser.parse_args(argv)
    try:
        if args.report and args.report.resolve() in {
            args.left.resolve(),
            args.right.resolve(),
        }:
            raise ValueError("Comparison report must not overwrite an input edition")
        report = compare_editions(
            args.left, args.right, title=args.title, author=args.author
        )
        if args.report:
            write_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
