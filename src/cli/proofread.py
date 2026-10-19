"""Check an existing edition against readable Jinjiang chapters without replacing it."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.output import run_command
from src.workflows.proofread import apply_proofread, prepare_proofread, review_proofread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="Read current content and collect Jinjiang layout evidence"
    )
    original = plan.add_mutually_exclusive_group(required=True)
    original.add_argument("--notion", help="Existing Notion work URL/ID")
    original.add_argument(
        "--input", type=Path, help="Existing EPUB or shared source.json"
    )
    plan.add_argument(
        "--jinjiang",
        help="Jinjiang book URL/ID; defaults to the book's source property",
    )
    plan.add_argument(
        "--config", type=Path, default=Path("book_specs/notion/config.json")
    )
    plan.add_argument(
        "--flagged",
        type=Path,
        help="Optional JSON array of {member,index,reason} suspect paragraphs",
    )
    review = commands.add_parser(
        "review", help="Use Codex to review suspect text against captured evidence"
    )
    apply = commands.add_parser(
        "apply",
        help="Apply formatting and high-confidence reviewed repairs, then read back",
    )
    apply.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Default: state/notion/proofread under the work root",
    )
    for command in (plan, review, apply):
        command.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_command(lambda: proofread(args))


def proofread(args: argparse.Namespace) -> dict:
    if args.command == "plan":
        result = prepare_proofread(
            args.run_dir,
            notion=args.notion,
            input_path=args.input,
            jinjiang=args.jinjiang,
            config_path=args.config,
            flagged=args.flagged,
        )
    elif args.command == "review":
        decisions = review_proofread(args.run_dir)
        result = {
            "reviewed": len(decisions["reviews"]),
            "decisions": str(args.run_dir / "decisions.json"),
        }
    else:
        result = apply_proofread(args.run_dir, state_root=args.state_root)
    return {"command": args.command, "result": result}


if __name__ == "__main__":
    raise SystemExit(main())
