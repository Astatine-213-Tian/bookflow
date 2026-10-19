"""Apply an explicit change JSON to a current book and write selected outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.output import paths, run_command
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
    return run_command(lambda: update(args))


def update(args: argparse.Namespace) -> dict:
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
    result = update_book(args.source, args.change, args.run_dir, outputs=outputs)
    check = result.epub_check
    return {
        "outputs": paths(
            source=result.source_path, epub=result.epub_path, txt=result.txt_path
        ),
        "epub_check": list(check.issues) if check else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
