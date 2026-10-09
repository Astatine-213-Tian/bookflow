"""Collect layout evidence, retaining access failures separately from content."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from src.metadata.jjwxc import novel_id_from_url, parse_jjwxc_contents
from src.runtime.files import write_json

CATALOG_JS = """(() => ({url: location.href, html: document.documentElement.outerHTML,
 title: document.querySelector('[itemprop="articleSection"]')?.textContent || document.title,
 author: document.querySelector('[itemprop="author"]')?.textContent || ''}))()"""
CHAPTER_JS = """(() => {
 const node = document.querySelector('#paragraph_comment_content') || document.querySelector('.noveltext');
 return {url: location.href, title: document.title, body_html: node?.innerHTML || '',
   note_html: document.querySelector('#note_str')?.innerHTML || '',
   note_present: !!document.querySelector('#note_str'),
   note_images: [...(document.querySelector('#note_str')?.querySelectorAll('img') || [])].map(n => ({src:n.src,alt:n.alt,loaded:n.complete && n.naturalWidth > 0})),
   login: /login\\.php/.test(location.pathname), purchase: /buynovel/.test(location.pathname),
   messages: (document.body.innerText.match(/.{0,15}(章节被锁|已被锁定|请输入验证码|访问过于频繁).{0,35}/g) || [])};
})()"""


def reference_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if not value.isdigit() and not (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"www.jjwxc.net", "my.jjwxc.net", "jjwxc.net"}
    ):
        raise ValueError("Reference must be a Jinjiang novel ID or desktop book URL")
    novel_id = novel_id_from_url(value)
    if not novel_id.isdigit():
        raise ValueError("Reference requires a numeric novelid")
    return novel_id, f"https://www.jjwxc.net/onebook.php?novelid={novel_id}"


def parse_body(markup: str) -> list[dict]:
    """Paragraph spans delimit prose; only intervening BRs establish scene gaps.

    Font-obfuscated characters remain unchanged. They can support masked layout
    matching, but must never be used as replacement text.
    """
    soup = BeautifulSoup(markup, "html.parser")
    paragraphs = soup.select(".onebook_paragraph_comment_text")
    if not paragraphs:
        raise ValueError("Unrecognized Jinjiang body layout; inspect before collecting")
    blocks = []
    previous = None
    for paragraph in paragraphs:
        text = paragraph.get_text().strip()
        # This provider's inline watermark is injected into its paragraph spans.
        text = re.sub(r"@(?:无限好文，尽在晋江文学城|晋江文学城)", "", text).strip()
        if not text:
            continue
        if previous is not None:
            gap = 0
            for node in previous.next_elements:
                if node is paragraph:
                    break
                if getattr(node, "name", None) == "br":
                    gap += 1
            blocks.extend(
                {"kind": "paragraph", "runs": []} for _ in range(max(0, gap - 1))
            )
        blocks.append({"kind": "paragraph", "runs": [{"text": text, "styles": []}]})
        previous = paragraph
    if not blocks:
        raise ValueError("Jinjiang returned no readable paragraphs")
    return blocks


def access_status(snapshot: dict, *, novel_id: str, chapter_id: str) -> str:
    parsed = urlparse(snapshot["url"])
    if snapshot.get("login") or "login.php" in parsed.path:
        return "login_required"
    if snapshot.get("purchase") or "buynovel" in parsed.path:
        return "purchase_page"
    if snapshot.get("messages"):
        return "blocked_or_locked"
    query = parse_qs(parsed.query)
    if query.get("novelid") != [novel_id] or query.get("chapterid") != [chapter_id]:
        return "wrong_chapter"
    if not snapshot.get("body_html"):
        return "body_unavailable"
    try:
        parse_body(snapshot["body_html"])
    except ValueError:
        return "unrecognized_body"
    return "readable"


def collect_in_browser(
    value: str, output: Path, *, new_tab, goto_url, wait_for_load, js
) -> None:
    """Called inside the verified arc-cdp browser-harness adapter, one tab only."""
    novel_id, url = reference_url(value)
    evidence_path = output / "evidence.json"
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    if evidence and evidence.get("source_url") != url:
        raise ValueError("Reference directory belongs to a different book")
    evidence = {"source_url": url, "chapters": evidence.get("chapters", {})}
    new_tab(url)
    wait_for_load()
    catalog = js(CATALOG_JS)
    contents = parse_jjwxc_contents(catalog["html"], novel_id=novel_id)
    evidence["catalog"] = contents.to_dict()
    write_json(evidence_path, evidence)
    chapters = [ch for v in contents.volumes for ch in v.chapters]
    # Test a real VIP chapter before a long collection. Recheck even on resume.
    soup = BeautifulSoup(catalog["html"], "html.parser")
    vip_numbers = {
        int(row.find("td").get_text(strip=True))
        for row in soup.select('tr[itemprop~="chapter"]')
        if "[VIP]" in row.get_text() and row.find("td").get_text(strip=True).isdigit()
    }
    probe = next(
        (ch for ch in reversed(chapters) if ch.number in vip_numbers and ch.url), None
    )

    def capture(chapter):
        if not chapter.url:
            return {"url": "", "status": "locked_or_unlinked"}
        goto_url(chapter.url)
        wait_for_load()
        state = {}
        for attempt in range(5):
            state = js(CHAPTER_JS)
            state["status"] = access_status(
                state, novel_id=novel_id, chapter_id=str(chapter.number)
            )
            if state["status"] not in {"body_unavailable", "unrecognized_body"}:
                break
            time.sleep(0.5)
        state["captured_at"] = time.time()
        state["capture_version"] = 2
        return state

    if probe:
        check = capture(probe)
        evidence["access_probe"] = {k: v for k, v in check.items() if k != "body_html"}
        write_json(evidence_path, evidence)
        if check["status"] != "readable":
            raise ValueError(
                f"Jinjiang access: {check['status']} at chapter {probe.number}; no subscription inference"
            )
    evidence["title"] = catalog["title"].strip()
    evidence["author"] = catalog["author"].strip()
    for index, chapter in enumerate(chapters):
        key = str(chapter.number)
        state = evidence["chapters"].get(key, {})
        # Only successful captures are reusable; failed access is always retried.
        if (
            state.get("status") != "readable"
            or state.get("requested_url") != chapter.url
            or state.get("capture_version") != 2
        ):
            state = capture(chapter)
            state["requested_url"] = chapter.url
            evidence["chapters"][key] = state
            write_json(evidence_path, evidence)
        if state["status"] == "login_required":
            raise ValueError(
                "Jinjiang login expired during collection; resume after login"
            )
        print(
            f"Jinjiang {index + 1}/{len(chapters)}: {chapter.number} {state['status']}",
            flush=True,
        )
    evidence["readable"] = sum(
        evidence["chapters"][str(ch.number)]["status"] == "readable" for ch in chapters
    )
    evidence["total"] = len(chapters)
    write_json(evidence_path, evidence)


def collect_reference(value: str, output: Path) -> Path:
    reference_url(value)
    adapters = subprocess.run(
        ["arc-cdp", "adapters"], check=True, capture_output=True, text=True
    )
    if "browser-harness" not in adapters.stdout.splitlines():
        raise ValueError("arc-cdp has no browser-harness adapter")
    root = str(Path(__file__).resolve().parents[4])
    program = (
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, {root!r})\n"
        "from src.crawler.providers.jjwxc.reference import collect_in_browser\n"
        f"collect_in_browser({value!r}, Path({str(output.resolve())!r}), "
        "new_tab=new_tab, goto_url=goto_url, wait_for_load=wait_for_load, js=js)\n"
    )
    # The harness's Python environment needs the project's installed dependencies.
    import os

    env = dict(os.environ)
    import site

    env["PYTHONPATH"] = os.pathsep.join([root, *site.getsitepackages()])
    subprocess.run(
        ["arc-cdp", "run", "browser-harness"],
        input=program,
        text=True,
        env=env,
        check=True,
    )
    from src.content.contract import metadata_defaults, validate_book

    evidence = json.loads((output / "evidence.json").read_text())
    novel_id, url = reference_url(value)
    book = {
        "version": 3,
        "identifier": f"jjwxc:{novel_id}",
        "source_format": "crawl",
        "metadata": metadata_defaults(
            {
                "title": evidence["title"],
                "creator": evidence["author"],
                "source": url,
                "language": "zh-CN",
            }
        ),
        "chapters": {},
        "sections": [],
        "extras": [],
    }
    for volume in evidence["catalog"]["volumes"]:
        for chapter in volume["chapters"]:
            state = evidence["chapters"][str(chapter["number"])]
            if state["status"] != "readable":
                continue
            member = f"chapter-{chapter['number']}"
            book["chapters"][member] = {
                "title": chapter["title"],
                "blocks": parse_body(state["body_html"]),
                "source": {"id": str(chapter["number"]), "url": state["url"]},
            }
            book["sections"].append({"member": member})
    validate_book(book)
    write_json(output / "source.json", book)
    return output / "source.json"
