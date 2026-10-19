"""Upload prepared books, verify drafts and recover Notion imports through official MCP and REST."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.cli.output import paths, run_command
from src.content.prepared import load_prepared_source
from src.notion.cms import CONFIG
from src.notion.duplicates import resolve_extra
from src.notion.mcp import (
    AUTH_FILE,
    TokenStore,
    connect,
    error_message,
    exclusive_lock,
    login,
)
from src.notion.upload import upload_draft, upload_source
from src.runtime.files import write_json


async def resume(state: Path, config_path: Path) -> dict:
    from src.notion.api import api_token

    api_token()
    config = json.loads(config_path.read_text())
    with exclusive_lock(state.parent / "import.lock"):
        book = json.loads(state.read_text())
        store = TokenStore(AUTH_FILE)
        with store.locked():
            async with connect(store) as tools:
                await upload_draft(book, state, config, tools=tools)
        return {
            "verified": True,
            "notion_url": "https://www.notion.so/" + book["work_id"],
            "outputs": paths(state=state),
        }


async def inspect_state(
    command: str, state: Path, config_path: Path, report: Path | None
) -> dict:
    from src.notion.recovery import recover_template
    from src.notion.verification import verify_draft

    config = json.loads(config_path.read_text())
    with exclusive_lock(state.parent / "import.lock"):
        book = json.loads(state.read_text())
        store = TokenStore(AUTH_FILE)
        with store.locked():
            async with connect(store) as tools:
                if command == "verify-cover":
                    from src.notion.cover import verify_cover

                    await verify_cover(book, state, tools=tools)
                    return {"cover_verified": True}
                if command == "recover-template":
                    await recover_template(book, state, config, tools=tools)
                    return {
                        "template_ready": True,
                        "next": f"book-notion resume --state {state}",
                    }
                result = await verify_draft(book, config, tools=tools)
                if report:
                    write_json(report, result)
                return {"verification": result, "outputs": paths(report=report)}


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
        help="Prepared source.json from book-prepare or a reviewed crawl",
    )
    covers = parser.add_mutually_exclusive_group()
    covers.add_argument(
        "--cover",
        type=Path,
        help="PNG/JPEG; API token or maintained browser cover procedure",
    )
    covers.add_argument("--cover-url", help="Public PNG/JPEG URL; attaches through MCP")
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
    if args.command in {"export", "update", "verify"}:
        from src.notion.api import api_token

        api_token()
    if args.command in {"export", "update"}:
        if not args.state:
            parser.error("export/update requires --state")
        if args.command == "update" and not args.change:
            parser.error("update requires --change")

        async def edit():
            from src.notion.update import apply_update, read_current

            with exclusive_lock(args.state.parent / "import.lock"):
                store = TokenStore(AUTH_FILE)
                with store.locked():
                    async with connect(store) as tools:
                        result = (
                            await apply_update(
                                args.state,
                                json.loads(args.change.read_text()),
                                json.loads(args.config.read_text()),
                                tools=tools,
                            )
                            if args.command == "update"
                            else await read_current(
                                json.loads(args.state.read_text()), tools=tools
                            )
                        )
                if args.report:
                    write_json(args.report, result)
                    return {"outputs": paths(report=args.report)}
                return {"result": result}

        return asyncio.run(edit())
    if args.command != "resolve-extra" and (
        args.extra is not None or args.use_existing or args.create_new
    ):
        parser.error("Duplicate-review options require resolve-extra")
    if args.report and args.command != "verify":
        parser.error("--report requires verify")
    if args.command == "upload":
        if args.source is None or args.state is not None:
            parser.error("upload requires --source and does not accept --state")
        source, prepared_cover, _ = load_prepared_source(args.source)
        state = upload_source(
            source,
            cover_bytes=args.cover.read_bytes()
            if args.cover
            else prepared_cover
            if not args.cover_url
            else None,
            cover_url=args.cover_url,
            config_path=args.config,
        )
        return {"outputs": paths(state=state)}
    if args.source or args.cover or args.cover_url:
        parser.error("--source and cover options require upload")
    if args.command in {"verify", "verify-cover", "recover-template"}:
        if args.state is None:
            parser.error(f"{args.command} requires --state")
        return asyncio.run(
            inspect_state(args.command, args.state, args.config, args.report)
        )
    if args.command == "resolve-extra":
        if (
            args.state is None
            or args.extra is None
            or not (args.use_existing or args.create_new)
        ):
            parser.error(
                "resolve-extra requires --state, --extra and --use-existing or --create-new"
            )
        with exclusive_lock(args.state.parent / "import.lock"):
            resolve_extra(args.state, args.extra, use_existing=args.use_existing)
        return {
            "resolved_extra": args.extra,
            "next": f"book-notion resume --state {args.state}",
        }
    if args.extra is not None or args.use_existing or args.create_new:
        parser.error("Duplicate-review options require resolve-extra")
    if args.command == "resume":
        if args.state is None:
            parser.error("resume requires --state")
        return asyncio.run(resume(args.state, args.config))
    store = TokenStore(AUTH_FILE)
    with store.locked():
        if args.command == "login":
            asyncio.run(login(store))
            return {"logged_in": True}
        store.clear_tokens()
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
