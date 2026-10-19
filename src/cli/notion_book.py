"""Upload prepared books, verify drafts and recover Notion imports through official MCP and REST."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cli.output import paths, run_command
from src.notion.cms import CONFIG
from src.notion.mcp import error_message
from src.runtime.files import write_json
from src.workflows import notion


def run(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "login",
            "export",
            "update",
            "logout",
            "upload",
            "resume",
            "verify",
            "verify-cover",
            "recover-template",
            "resolve-extra",
        ],
    )
    parser.add_argument(
        "--state", type=Path, help="state/notion/.../import.json"
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument(
        "--source",
        type=Path,
        help="Prepared source.json from book prepare or a reviewed crawl",
    )
    covers = parser.add_mutually_exclusive_group()
    covers.add_argument(
        "--cover",
        type=Path,
        help="User-approved 2:3 PNG/JPEG replacing the prepared cover",
    )
    covers.add_argument("--cover-url", help="Public PNG/JPEG URL; attaches through MCP")
    covers.add_argument(
        "--keep-original-cover",
        action="store_true",
        help="Skip cover normalization for an art book or approved exception",
    )
    parser.add_argument("--report", type=Path, help="Fresh verification report")
    parser.add_argument(
        "--extra", type=int, help="1-based extra index in extra-review.md"
    )
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--use-existing", help="Reviewed shared-extra page ID or URL")
    decision.add_argument(
        "--create-new",
        action="store_true",
        help="Confirm this extra is separate content",
    )
    parser.add_argument("--change", type=Path, help="Explicit chapter change JSON")
    args = parser.parse_args(argv)
    resume = f"book notion resume --state {args.state}"
    if args.command in {"export", "update"}:
        if not args.state:
            parser.error("export/update requires --state")
        if args.command == "update" and not args.change:
            parser.error("update requires --change")
        result = (
            notion.update(args.state, args.change, args.config)
            if args.command == "update"
            else notion.export(args.state)
        )
        if args.report:
            write_json(args.report, result)
            return {"outputs": paths(report=args.report)}
        return {"result": result}
    if args.command != "resolve-extra" and (
        args.extra is not None or args.use_existing or args.create_new
    ):
        parser.error("Duplicate-review options require resolve-extra")
    if args.report and args.command != "verify":
        parser.error("--report requires verify")
    if args.command == "upload":
        if args.source is None or args.state is not None:
            parser.error("upload requires --source and does not accept --state")
        state = notion.upload(
            args.source,
            cover=args.cover,
            cover_url=args.cover_url,
            keep_original_cover=args.keep_original_cover,
            config_path=args.config,
        )
        return {"outputs": paths(state=state)}
    if args.source or args.cover or args.cover_url or args.keep_original_cover:
        parser.error("--source and cover options require upload")
    if args.command in {"verify", "verify-cover", "recover-template", "resume"}:
        if args.state is None:
            parser.error(f"{args.command} requires --state")
    if args.command == "verify":
        result = notion.verify(args.state, args.config, args.report)
        return {"verification": result, "outputs": paths(report=args.report)}
    if args.command == "verify-cover":
        notion.verify_cover(args.state)
        return {"cover_verified": True}
    if args.command == "recover-template":
        notion.recover_template(args.state, args.config)
        return {"template_ready": True, "next": resume}
    if args.command == "resolve-extra":
        if (
            args.state is None
            or args.extra is None
            or not (args.use_existing or args.create_new)
        ):
            parser.error(
                "resolve-extra requires --state, --extra and --use-existing or --create-new"
            )
        notion.resolve_shared_extra(args.state, args.extra, args.use_existing)
        return {"resolved_extra": args.extra, "next": resume}
    if args.command == "resume":
        result = notion.resume(args.state, args.config)
        return {"verified": True, **result, "outputs": paths(state=args.state)}
    if args.command == "login":
        notion.login()
        return {"logged_in": True}
    notion.logout()
    return {"tokens_removed": True}


def main(argv: list[str] | None = None) -> int:
    # error_message sanitizes SDK errors at the CLI boundary.
    return run_command(
        lambda: run(argv),
        describe=error_message,
        interrupted="Interrupted; resume the saved draft checkpoint",
    )


if __name__ == "__main__":
    raise SystemExit(main())
