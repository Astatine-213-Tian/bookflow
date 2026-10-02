"""Upload prepared books, verify drafts and recover Notion imports through MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

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


async def resume(state: Path, config_path: Path) -> None:
    config = json.loads(config_path.read_text())
    with exclusive_lock(state.parent / "import.lock"):
        book = json.loads(state.read_text())
        store = TokenStore(AUTH_FILE)
        with store.locked():
            async with connect(store) as tools:
                await upload_draft(book, state, config, tools=tools)
        print("CMS draft verified: https://www.notion.so/" + book["work_id"])


async def inspect_state(
    command: str, state: Path, config_path: Path, report: Path | None
) -> None:
    from src.notion.recovery import recover_template
    from src.notion.verification import verify_draft

    config = json.loads(config_path.read_text())
    with exclusive_lock(state.parent / "import.lock"):
        book = json.loads(state.read_text())
        store = TokenStore(AUTH_FILE)
        with store.locked():
            async with connect(store) as tools:
                if command == "recover-template":
                    await recover_template(book, state, config, tools=tools)
                    print("Template ready; resume the existing checkpoint")
                else:
                    result = await verify_draft(book, config, tools=tools)
                    if report:
                        write_json(report, result)
                    print(json.dumps(result, ensure_ascii=False, indent=2))


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "login",
            "logout",
            "upload",
            "resume",
            "verify",
            "recover-template",
            "resolve-extra",
        ],
    )
    parser.add_argument(
        "--state", type=Path, help="generated/notion_cms_sources/.../import.json"
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument(
        "--source",
        type=Path,
        help="Prepared source.json from book-prepare or a reviewed crawl",
    )
    covers = parser.add_mutually_exclusive_group()
    covers.add_argument(
        "--cover", type=Path, help="PNG/JPEG; requires NOTION_API_TOKEN"
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
    args = parser.parse_args(argv)
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
        print(f"Import checkpoint: {state}")
        return
    if args.source or args.cover or args.cover_url:
        parser.error("--source and cover options require upload")
    if args.command in {"verify", "recover-template"}:
        if args.state is None:
            parser.error(f"{args.command} requires --state")
        asyncio.run(inspect_state(args.command, args.state, args.config, args.report))
        return
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
        return
    if args.extra is not None or args.use_existing or args.create_new:
        parser.error("Duplicate-review options require resolve-extra")
    if args.command == "resume":
        if args.state is None:
            parser.error("resume requires --state")
        asyncio.run(resume(args.state, args.config))
        return
    store = TokenStore(AUTH_FILE)
    with store.locked():
        if args.command == "login":
            asyncio.run(login(store))
        else:
            store.clear_tokens()
            print("Local Notion MCP tokens removed")


def main(argv: list[str] | None = None) -> None:
    try:
        run(argv)
    except KeyboardInterrupt:
        raise SystemExit("Interrupted; resume the saved draft checkpoint") from None
    except Exception as error:  # noqa: BLE001 - sanitize SDK errors at the CLI boundary
        raise SystemExit(error_message(error)) from None


if __name__ == "__main__":
    main()
