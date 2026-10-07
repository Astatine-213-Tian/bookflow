"""Apply an explicit change JSON to a current book and write selected outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.workflows.ingest import OutputOptions
from src.workflows.update import update_book


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--change", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mode", action="append", choices=["epub", "txt"], default=[])
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--txt-output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        outputs = (
            OutputOptions(
                output=args.output,
                txt_output=args.txt_output,
                output_formats=tuple(args.mode),
                prevent_overwrite=not args.overwrite,
            )
            if args.mode or args.output or args.txt_output
            else None
        )
        candidate = update_book(args.source, args.change, args.run_dir, outputs=outputs)
        print(candidate)
        return 0
    except (ValueError, OSError) as error:
        print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
