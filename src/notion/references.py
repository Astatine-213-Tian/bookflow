"""Bind portable references to real Notion blocks and verify both link directions."""

from __future__ import annotations

import copy
import json
import subprocess
from difflib import SequenceMatcher
from typing import Callable

from notion_books import NotionBooks, to_markdown, from_markdown

from src.content.blocks import content_signature
from src.notion.capabilities import read_content
from src.notion.mcp import finish_write


def plain_references(blocks: list[dict]) -> list[dict]:
    result = copy.deepcopy(blocks)
    for b in result:
        b.pop("anchor", None)
        b.pop("footnote", None)
        for r in b["runs"]:
            if r.get("href", "").startswith("#"):
                r.pop("href")
                r.pop("link_role", None)
    return result


def bind_references(blocks: list[dict], bindings: dict[str, str]) -> list[dict]:
    result = copy.deepcopy(blocks)
    for block in result:
        for run in block["runs"]:
            if run.get("href", "").startswith("#"):
                key = run["href"][1:]
                if key not in bindings:
                    raise ValueError(f"No verified Notion destination for {key}")
                run["href"] = (
                    bindings.get("chapter:" + key, bindings[key])
                    if not run.get("link_role")
                    else bindings[key]
                )
    return result


def expected_content(blocks: list[dict], bindings: dict[str, str]) -> list[dict]:
    return read_content(to_markdown(bind_references(blocks, bindings)))


def wire_signature(markdown: str):
    """Compare native destination URLs before converting them to portable IDs."""
    return content_signature(from_markdown(markdown, preserve_links=True))


def verify_bound_content(
    markdown: str, blocks: list[dict], bindings: dict[str, str]
) -> bool:
    return wire_signature(markdown) == wire_signature(
        to_markdown(bind_references(blocks, bindings))
    )


class AnchorBrowser:
    """Read native block IDs via the maintained Arc adapter; own one task tab."""

    def __init__(self):
        self.target = None

    def snapshot(self, page_id: str, expected: list[dict] | None = None) -> list[dict]:
        import re

        if not re.fullmatch(r"[a-fA-F0-9-]{32,36}", page_id):
            raise ValueError("Invalid Notion page ID")
        code = "import json,time\n"
        if self.target:
            code += f"switch_tab({self.target!r})\ngoto_url({('https://app.notion.com/p/' + page_id.replace('-', ''))!r})\n"
        else:
            code += f"target=new_tab({('https://app.notion.com/p/' + page_id.replace('-', ''))!r})\n"
        code += "wait_for_load()\n"
        expected_texts = [
            "".join(r["text"] for r in b["runs"]).replace("\r\n", "\n").strip()
            for b in (expected or [])
            if "".join(r["text"] for r in b["runs"]).strip()
        ]
        code += f"expected={expected_texts!r}\n"
        # DOM attributes are needed here: AX does not expose native block IDs.
        expression = """Array.from(document.querySelectorAll('.notion-page-content [contenteditable="true"]')).map(e=>({text:e.innerText.replace(/\\uFEFF/g,''),id:e.closest('[data-block-id]')?.getAttribute('data-block-id')})).filter(x=>x.id)"""
        code += f"""rows=[]
for attempt in range(30):
    rows=js({expression!r})
    if rows and (not expected or [r["text"].replace("\\r\\n","\\n").strip() for r in rows if r["text"].strip()]==expected): break
    time.sleep(0.5)
print('BOOK_ANCHORS:'+json.dumps({{'target':current_tab()['targetId'],'rows':rows}},ensure_ascii=False))
"""
        p = subprocess.run(
            ["arc-cdp", "run", "browser-harness"],
            input=code,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if p.returncode:
            raise ValueError(
                "Notion block inspection failed through arc-cdp browser-harness"
            )
        line = next(
            (s for s in p.stdout.splitlines() if s.startswith("BOOK_ANCHORS:")), None
        )
        if not line:
            raise ValueError("Notion block inspection returned no snapshot")
        data = json.loads(line.split(":", 1)[1])
        self.target = data["target"]
        if not data["rows"]:
            raise ValueError("Notion page not loaded or login required")
        return data["rows"]

    def close(self):
        if self.target:
            subprocess.run(
                ["arc-cdp", "run", "browser-harness"],
                input=f"close_tab({self.target!r})\n",
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.target = None


def anchor_bindings(
    page_id: str, blocks: list[dict], snapshot: list[dict]
) -> dict[str, str]:
    """Require the complete visible text sequence before associating any ID."""
    expected = [b for b in blocks if "".join(r["text"] for r in b["runs"]).strip()]
    observed = [r for r in snapshot if r["text"].strip()]

    def normalize(text):
        return text.replace("\r\n", "\n").strip()

    if [normalize("".join(r["text"] for r in b["runs"])) for b in expected] != [
        normalize(r["text"]) for r in observed
    ]:
        raise ValueError(
            "Browser block text/order differs from the verified manuscript"
        )
    return {
        b["anchor"]: "https://www.notion.so/"
        + page_id.replace("-", "")
        + "#"
        + row["id"].replace("-", "")
        for b, row in zip(expected, observed)
        if b.get("anchor")
    }


def content_updates(before: str, after: str) -> list[dict]:
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    edits = []
    for kind, a, b, c, d in SequenceMatcher(
        None, old, new, autojunk=False
    ).get_opcodes():
        if kind == "equal":
            continue
        old_str, new_str = "".join(old[a:b]), "".join(new[c:d])
        if not old_str or before.count(old_str) != 1:
            raise ValueError(
                "Reference edit is not unique; reconcile this page before writing"
            )
        edits.append({"old_str": old_str, "new_str": new_str})
    return edits


async def link_page(
    page_id: str,
    blocks: list[dict],
    bindings: dict[str, str],
    *,
    tools,
    snapshot: Callable[[str], list[dict]],
) -> None:
    reader = NotionBooks(tools)
    before = await reader.document(page_id)
    actual = read_content(before.markdown)
    if verify_bound_content(before.markdown, blocks, bindings):
        live = anchor_bindings(page_id, blocks, snapshot(page_id))
        if any(bindings[key] != url for key, url in live.items()):
            raise ValueError("Notion reference target IDs changed")
        return

    # Only add hyperlinks after the entire staged text and formatting read back.
    def visible(value):
        out = copy.deepcopy(value)
        for b in out:
            b.pop("anchor", None)
            b.pop("footnote", None)
            for r in b["runs"]:
                if (
                    r.get("link_role")
                    or r.get("href", "").startswith("#")
                    or r.get("href") in bindings.values()
                ):
                    r.pop("href", None)
                    r.pop("link_role", None)
        return content_signature(out)

    if visible(actual) != visible(blocks):
        raise ValueError("Manuscript changed before reference binding")
    markdown = to_markdown(bind_references(blocks, bindings))
    edits = content_updates(before.markdown, markdown)
    if edits:
        await finish_write(
            tools,
            "notion-update-page",
            {"page_id": page_id, "command": "update_content", "content_updates": edits},
        )
    after = await reader.document(page_id)
    if not verify_bound_content(after.markdown, blocks, bindings):
        raise ValueError("Notion hyperlink readback differs")
    live = anchor_bindings(page_id, blocks, snapshot(page_id))
    if any(bindings[key] != url for key, url in live.items()):
        raise ValueError(
            "Notion changed block IDs while binding references; preserve checkpoint and rebind to fresh IDs"
        )


async def finish_references(book: dict, state, *, tools, browser=None) -> None:
    """Second upload pass: resolve anchors only after every chapter exists."""
    from src.runtime.files import write_json

    reader = NotionBooks(tools)
    rows = [*book["chapters"].values(), *book.get("extras", [])]
    if not any(
        r.get("href", "").startswith("#")
        for ch in rows
        for b in ch["blocks"]
        for r in b["runs"]
    ):
        return
    own_browser = browser is None
    browser = browser or AnchorBrowser()
    try:
        bindings = {}
        for ch in rows:
            if not any(b.get("anchor") for b in ch["blocks"]):
                continue
            page_id = ch["page_id"]
            page = await reader.document(page_id)
            actual = read_content(page.markdown)
            expected = read_content(to_markdown(plain_references(ch["blocks"])))

            # A resumed pass may already contain links. Compare visible content
            # before collecting IDs; the write itself checks every link later.
            def strip_links(blocks):
                blocks = copy.deepcopy(blocks)
                for b in blocks:
                    b.pop("anchor", None)
                    b.pop("footnote", None)
                    for r in b["runs"]:
                        if (
                            r.get("link_role")
                            or r.get("href", "").startswith("#")
                            or r.get("href")
                            in book.get("reference_bindings", {}).values()
                        ):
                            r.pop("href", None)
                            r.pop("link_role", None)
                return content_signature(blocks)

            if strip_links(actual) != strip_links(expected):
                raise ValueError("Content changed before anchor collection")
            bindings.update(
                anchor_bindings(
                    page_id, ch["blocks"], browser.snapshot(page_id, ch["blocks"])
                )
            )
            first = next(
                (
                    b
                    for b in ch["blocks"]
                    if "".join(r["text"] for r in b["runs"]).strip()
                ),
                None,
            )
            if first and first.get("anchor"):
                bindings["chapter:" + first["anchor"]] = (
                    "https://www.notion.so/" + page_id.replace("-", "")
                )
        book["reference_bindings"] = bindings
        write_json(state, book)
        for ch in rows:
            if not any(
                r.get("href", "").startswith("#")
                for b in ch["blocks"]
                for r in b["runs"]
            ):
                continue
            await link_page(
                ch["page_id"],
                ch["blocks"],
                bindings,
                tools=tools,
                snapshot=lambda page_id: browser.snapshot(page_id, ch["blocks"]),
            )
            ch.pop("references_pending", None)
            write_json(state, book)
    finally:
        if own_browser:
            browser.close()


def _content_rows(book: dict) -> dict[tuple[str, str], dict]:
    """Index reading units without mixing transport IDs into content identity."""
    return {
        **{("chapter", key): ch for key, ch in book["chapters"].items()},
        **{
            (("extra", ch["id"]) if ch.get("id") else ("extra-index", str(index))): ch
            for index, ch in enumerate(book.get("extras", []))
        },
    }


def checkpoint_page_ids(checkpoint: dict) -> dict[tuple[str, str], str]:
    return {
        key: ch["page_id"]
        for key, ch in _content_rows(checkpoint).items()
        if ch.get("page_id")
    }


def localize_chapter_links(book: dict, page_ids: dict[tuple[str, str], str]) -> None:
    """Restore portable links among chapter and independent-extra page starts."""
    import re
    from urllib.parse import urlsplit
    from src.runtime.files import digest

    reverse = {value.replace("-", ""): key for key, value in page_ids.items()}
    rows = _content_rows(book)
    for chapter in rows.values():
        for block in chapter["blocks"]:
            for run in block["runs"]:
                u = urlsplit(run.get("href", ""))
                if (
                    u.hostname not in {"www.notion.so", "notion.so", "app.notion.com"}
                    or u.fragment
                ):
                    continue
                m = re.search(r"([a-f0-9]{32}|[a-f0-9-]{36})$", u.path)
                target = reverse.get(m[1].replace("-", "")) if m else None
                if target not in rows:
                    continue
                first = next(
                    (
                        b
                        for b in rows[target]["blocks"]
                        if "".join(r["text"] for r in b["runs"]).strip()
                    ),
                    None,
                )
                if first is None:
                    raise ValueError("Linked chapter has no readable content")
                identity = json.dumps(target, ensure_ascii=False)
                first.setdefault("anchor", "chapter-" + digest(identity.encode())[:20])
                run["href"] = "#" + first["anchor"]
