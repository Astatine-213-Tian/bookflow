"""Resolve source anchors after chapter selection, without destination IDs."""

from __future__ import annotations

import posixpath
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

from src.runtime.files import digest

EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


def source_href(member: str, href: str, *, base_url: str | None = None) -> str:
    parsed = urlsplit(href)
    if base_url:
        # A bare fragment belongs to this extracted chapter even when several
        # chapters share the same fallback book URL.
        if href.startswith("#"):
            return member + "#" + unquote(parsed.fragment)
        return urljoin(base_url, href)
    if parsed.scheme or parsed.netloc:
        return href
    target = (
        posixpath.normpath(
            posixpath.join(posixpath.dirname(member), unquote(parsed.path))
        )
        if parsed.path
        else member
    )
    return target + ("#" + unquote(parsed.fragment) if parsed.fragment else "")


def source_anchor(member: str, key: str) -> str:
    return "anchor-" + digest((member + "#" + key).encode())[:20]


def is_footnote(node) -> bool:
    semantics = set((node.get(EPUB_TYPE, "") + " " + node.get("role", "")).split())
    if semantics & {"footnote", "endnote", "doc-footnote", "doc-endnote"}:
        return True
    # EPUB 2 has no standard note semantics. Require a named destination, an
    # explicit note class AND a link back; a styled note-looking span is not enough.
    classes = node.get("class", "").lower().split()
    return bool(
        node.get("id")
        and any(c in {"footnote", "p_footnote", "endnote"} for c in classes)
        and node.xpath('.//*[local-name()="a"][@href]')
    )


def resolve_book_references(
    book: dict, inventory: dict, *, source_urls: dict[str, str] | None = None
) -> None:
    chapters = [*book["chapters"].values(), *book["extras"]]
    aliases = {}
    for member, anchors in inventory["anchors"].items():
        for name, index in anchors.items():
            if index < len(inventory["pages"][member]):
                block = inventory["pages"][member][index]
                if block.get("anchor"):
                    aliases[member + "#" + name] = block["anchor"]
    retained = {
        b["anchor"]: b for ch in chapters for b in ch["blocks"] if b.get("anchor")
    }
    origins = {
        block["anchor"]: member
        for member, originals in inventory["pages"].items()
        for block in originals
        if block.get("anchor")
    }
    for ch in chapters:
        for block in ch["blocks"]:
            if (
                block.get("anchor") in origins
                and "".join(r["text"] for r in block["runs"]).strip()
            ):
                aliases.setdefault(origins[block["anchor"]], block["anchor"])
    # Web sources may link to another collected chapter by its original URL.
    # Only bind an unambiguous document; repeated URLs can represent separate
    # excerpts, so their absolute links remain links to the original website.
    documents = {}
    for member, url in (source_urls or {}).items():
        if url:
            documents.setdefault(urldefrag(url)[0], []).append(member)
    unique_urls = {
        members[0]: url for url, members in documents.items() if len(members) == 1
    }
    for key, target in list(aliases.items()):
        member, separator, fragment = key.partition("#")
        if member in unique_urls:
            aliases[unique_urls[member] + separator + fragment] = target

    def destination(href: str) -> str | None:
        base, fragment = urldefrag(href)
        return aliases.get(href) or (
            aliases.get(base + "#" + unquote(fragment)) if fragment else None
        )

    incoming = {}
    for ch in chapters:
        for block in ch["blocks"]:
            for run in block["runs"]:
                target = destination(run.get("href", ""))
                if (
                    target in retained
                    and retained[target].get("footnote")
                    and not block.get("footnote")
                ):
                    incoming.setdefault(retained[target]["footnote"], set()).add(
                        block["anchor"]
                    )
    for ch in chapters:
        for block in ch["blocks"]:
            for run in block["runs"]:
                href = run.get("href")
                if not href:
                    continue
                parsed = urlsplit(href)
                target = destination(href)
                if target is None and (parsed.scheme or parsed.netloc):
                    continue
                if (
                    target is None
                    and "#" in href
                    and block.get("footnote")
                    and len(incoming.get(block["footnote"], set())) == 1
                ):
                    # Some EPUB 2 endnotes contain a backlink but omit its empty
                    # source anchor. A unique incoming note reference identifies
                    # the return paragraph without guessing from its prose.
                    target = next(iter(incoming[block["footnote"]]))
                    inventory.setdefault("reference_repairs", []).append(
                        {
                            "href": href,
                            "target": target,
                            "reason": "unique incoming footnote reference",
                        }
                    )
                if target not in retained:
                    raise ValueError(
                        f"Link target was omitted or cannot be resolved: {href}"
                    )
                if retained[target].get("footnote") and not block.get("footnote"):
                    # A source may point into a later paragraph of one note.
                    # Preparation joins that note, so use its stable group ID.
                    target = retained[target]["footnote"]
                    if target not in retained:
                        raise ValueError(f"Footnote destination was omitted: {href}")
                    run["link_role"] = "noteref"
                elif block.get("footnote") and target in incoming.get(
                    block["footnote"], set()
                ):
                    run["link_role"] = "backlink"
                run["href"] = "#" + target
    for ch in chapters:
        for block in ch["blocks"]:
            if block.get("footnote") and not incoming.get(block["footnote"]):
                inventory.setdefault("reference_repairs", []).append(
                    {
                        "anchor": block["footnote"],
                        "reason": "Unreferenced endnote retained as ordinary text",
                    }
                )
                block.pop("footnote")
    # Unreferenced navigation/title anchors need not enter the public content.
    used = {
        r["href"][1:]
        for ch in chapters
        for b in ch["blocks"]
        for r in b["runs"]
        if r.get("href", "").startswith("#")
    }
    # Canonical preparation creates return links even when the source note has
    # none. Keep the incoming paragraphs' anchors for that later step.
    used.update(anchor for references in incoming.values() for anchor in references)
    for ch in chapters:
        for b in ch["blocks"]:
            if b.get("anchor") not in used and not b.get("footnote"):
                b.pop("anchor", None)
