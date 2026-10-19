"""Check, normalize and review book covers (2:3, at most 1,000,000 bytes)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.output import paths, run_command
from src.content.cover import assess_cover, fit_restored_cover, normalize_cover

SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Report keep, crop or restore per cover")
    check.add_argument("paths", nargs="+", type=Path)
    normalize = commands.add_parser(
        "normalize", help="Write the delivered cover for a keep or crop verdict"
    )
    normalize.add_argument("path", type=Path)
    normalize.add_argument(
        "-o", "--output", type=Path, required=True, help="Output path without suffix"
    )
    normalize.add_argument(
        "--restored",
        action="store_true",
        help="Verify a restored 2:3 candidate and fit it to the byte limit",
    )
    review = commands.add_parser(
        "review", help="Build the comparison page for one restoration round"
    )
    review.add_argument("manifest", type=Path)
    review.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    return run_command(lambda: run(args))


def run(args: argparse.Namespace) -> dict:
    if args.command == "check":
        covers = [
            {"path": str(path), **assess_cover(path.read_bytes()).to_dict()}
            for path in args.paths
        ]
        restore = sum(c["verdict"] == "restore" for c in covers)
        return {"status": "issues_found" if restore else "complete", "covers": covers}
    if args.command == "normalize":
        data = args.path.read_bytes()
        if args.restored:
            encoded, mime = fit_restored_cover(data)
            assessment = None
        else:
            encoded, mime, found = normalize_cover(data)
            if found.verdict == "restore":
                return {"status": "issues_found", "cover": found.to_dict()}
            assessment = found.to_dict()
        output = args.output
        if output.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            output = output.with_suffix("")
        output = output.with_name(output.name + SUFFIX[mime])
        output.write_bytes(encoded)
        return {"outputs": paths(cover=output), "bytes": len(encoded), "cover": assessment}
    from src.workflows.cover_review import build_review

    output = args.output or args.manifest.with_name("review.html")
    return {"outputs": paths(review=build_review(args.manifest, output))}


if __name__ == "__main__":
    raise SystemExit(main())
