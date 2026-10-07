"""Extract EPUB 2/3 into content; reviewed ranges resolve ambiguous editions."""

from __future__ import annotations

import copy
import posixpath
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from src.content.contract import metadata_defaults
from src.epub.metadata import _find_opf_member, _package_metadata
from src.inputs.html import parse_xml, read_html_blocks
from src.inputs.references import resolve_book_references
from src.runtime.files import digest


@dataclass
class InputBook:
    source: dict
    cover: bytes | None = None
    cover_mime: str = "image/jpeg"
    evidence: dict | None = None


def inventory_epub(path: Path) -> dict:
    with ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError("Corrupt EPUB archive")
        opf = _find_opf_member(archive)
        files = {name: archive.read(name) for name in archive.namelist()}
    package = parse_xml(files[opf])

    def resolve(parent: str, href: str) -> tuple[str, str]:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or parsed.query:
            raise ValueError(f"Nonlocal EPUB resource: {href}")
        member = posixpath.normpath(
            posixpath.join(posixpath.dirname(parent), unquote(parsed.path))
        )
        if member not in files:
            raise ValueError(f"Missing EPUB resource: {member}")
        return member, unquote(parsed.fragment)

    manifest = {
        n.get("id"): (resolve(opf, n.get("href", ""))[0], n)
        for n in package.findall("{*}manifest/{*}item")
    }
    covers = [
        (m, n)
        for m, n in manifest.values()
        if "cover-image" in n.get("properties", "").split()
    ]
    if not covers:
        ids = package.xpath('//*[local-name()="meta" and @name="cover"]/@content')
        covers = [manifest[key] for key in ids if key in manifest]
    covers = list({m: (m, n) for m, n in covers}.values())
    if len(covers) > 1:
        raise ValueError("EPUB declares multiple covers")
    cover_member, cover_node = covers[0] if covers else (None, None)
    metadata = asdict(_package_metadata(files[opf]))
    metadata["creator"] = metadata.pop("author")
    creators = [
        "".join(node.itertext()).strip()
        for node in package.findall(
            "{*}metadata/{http://purl.org/dc/elements/1.1/}creator"
        )
    ]
    if len(creators) > 1:
        metadata["creators"] = creators
    metadata["subjects"] = list(metadata["subjects"])
    metadata = {key: value for key, value in metadata.items() if value is not None}
    metadata = metadata_defaults(metadata)
    pages, anchors, titles, identities, roles, block_evidence = {}, {}, {}, {}, {}, {}
    navs = [m for m, n in manifest.values() if "nav" in n.get("properties", "").split()]
    for ref in package.findall("{*}spine/{*}itemref"):
        member, item = manifest[ref.get("idref")]
        if member in navs:
            continue
        if member in pages or item.get("media-type") not in {
            "application/xhtml+xml",
            "text/html",
        }:
            raise ValueError(f"Duplicate or unsupported EPUB spine document: {member}")
        root = parse_xml(files[member])
        body = next(
            iter(root.xpath("//*[@data-book-chapter-id]")), root.find("{*}body")
        )
        identities[member] = (
            body.get("data-book-chapter-id") if body is not None else None
        )
        roles[member] = body.get("data-book-role") if body is not None else None
        found = {}
        block_evidence[member] = {}
        blocks = read_html_blocks(
            files[member], member, files, anchors=found, evidence=block_evidence[member]
        )
        if blocks and all(
            b["kind"] == "image" and b["asset"] == cover_member for b in blocks
        ):
            continue
        pages[member], anchors[member] = blocks, found
        titles[member] = root.findtext("{*}head/{*}title") or Path(member).stem
    toc = []
    if navs:
        nav = navs[0]
        root = parse_xml(files[nav])
        candidates = root.xpath(
            '//*[local-name()="nav" and @epub:type="toc"]',
            namespaces={"epub": "http://www.idpf.org/2007/ops"},
        )
        if len(candidates) != 1:
            raise ValueError("EPUB requires an unambiguous navigation table")

        def walk(ol):
            result = []
            for li in ol.findall("{*}li"):
                labels = [n for n in li if n.tag.rsplit("}", 1)[-1] in {"a", "span"}]
                if len(labels) != 1:
                    raise ValueError("Ambiguous navigation label")
                label = labels[0]
                title = "".join(label.itertext()).strip()
                children = li.find("{*}ol")
                if children is not None:
                    nested = walk(children)
                    if label.get("href"):
                        target = resolve(nav, label.get("href"))
                        first = nested[0] if nested else {}
                        while "children" in first:
                            first = first["children"][0]
                        if target != (first.get("member"), first.get("fragment", "")):
                            nested.insert(
                                0,
                                {
                                    "title": title,
                                    "member": target[0],
                                    "fragment": target[1],
                                },
                            )
                    result.append(
                        {
                            "title": title,
                            "children": nested,
                            **(
                                {"id": li.get("data-volume-id")}
                                if li.get("data-volume-id")
                                else {}
                            ),
                        }
                    )
                else:
                    member, fragment = resolve(nav, label.get("href", ""))
                    result.append(
                        {"title": title, "member": member, "fragment": fragment}
                    )
            return result

        toc = walk(candidates[0].find("{*}ol"))
    else:
        ncx = next(
            (
                m
                for m, n in manifest.values()
                if n.get("media-type") == "application/x-dtbncx+xml"
            ),
            None,
        )
        if ncx:

            def walk_ncx(parent):
                result = []
                for point in parent.findall("{*}navPoint"):
                    title = point.findtext("{*}navLabel/{*}text") or ""
                    member, fragment = resolve(ncx, point.find("{*}content").get("src"))
                    children = walk_ncx(point)
                    if children:
                        first = children[0]
                        while "children" in first:
                            first = first["children"][0]
                        if (member, fragment) != (
                            first.get("member"),
                            first.get("fragment", ""),
                        ):
                            children.insert(
                                0,
                                {
                                    "title": title,
                                    "member": member,
                                    "fragment": fragment,
                                },
                            )
                        result.append({"title": title, "children": children})
                    else:
                        result.append(
                            {"title": title, "member": member, "fragment": fragment}
                        )
                return result

            toc = walk_ncx(parse_xml(files[ncx]).find("{*}navMap"))
    return {
        "metadata": metadata,
        "pages": pages,
        "anchors": anchors,
        "titles": titles,
        "toc": toc,
        "files": files,
        "identities": identities,
        "roles": roles,
        "block_evidence": block_evidence,
        "identifier": package.findtext(".//{*}identifier"),
        "cover_member": cover_member,
        "cover_mime": cover_node.get("media-type")
        if cover_node is not None
        else "image/jpeg",
    }


def read_epub_source(path: Path, *, review: dict | None = None) -> InputBook:
    inventory = inventory_epub(path)
    pages, toc = inventory["pages"], inventory["toc"]
    evidence = {}
    book = {
        "version": 3,
        "identifier": inventory["identifier"]
        or "local-edition:" + digest(path.read_bytes()),
        "source_format": "epub",
        "metadata": inventory["metadata"],
        "sections": [],
        "chapters": {},
        "extras": [],
    }

    def chapter(
        key: str,
        title: str,
        blocks: list[dict],
        role: str = "chapter",
        *,
        start: int = 0,
    ) -> dict:
        member = key.split("#")[0]
        key = (
            inventory["identities"].get(member)
            if "#" not in key and inventory["identities"].get(member)
            else "chapter-" + digest(key.encode())[:16]
        )
        role = role if review is not None else inventory["roles"].get(member) or role
        blocks = copy.deepcopy(blocks)
        hints = [
            inventory["block_evidence"].get(member, {}).get(start + i, {})
            for i in range(len(blocks))
        ]
        if any(b["kind"] == "image" for b in blocks):
            raise ValueError(
                f"Body image in {key}; use --review to explicitly omit or transcribe it"
            )
        if (
            blocks
            and blocks[0]["kind"] == "heading"
            and "".join(r["text"] for r in blocks[0]["runs"]).strip() == title.strip()
        ):
            blocks.pop(0)
            hints.pop(0)
        if role == "chapter" and title.strip() == "简介":
            role = "intro"
        if key in book["chapters"] or any(x.get("id") == key for x in book["extras"]):
            raise ValueError(f"Duplicate chapter identity: {key}")
        book["chapters"][key] = {"title": title, "blocks": blocks, "role": role}
        evidence[key] = hints
        if role == "extra":
            book["chapters"][key]["id"] = key
        return {"member": key}

    if review is not None:
        if review.get("sha256") != digest(path.read_bytes()):
            raise ValueError("Review belongs to different input bytes")
        if set(review.get("pages", {})) != set(pages):
            raise ValueError("Review must account for every spine document")
        book["metadata"].update(review.get("metadata", {}))
        for member, blocks in pages.items():
            position = 0
            for index, part in enumerate(review["pages"][member]):
                start, stop = part["start"], part["stop"]
                if (
                    type(start) is not int
                    or type(stop) is not int
                    or start != position
                    or not start < stop <= len(blocks)
                ):
                    raise ValueError(f"Incomplete block coverage: {member}")
                position = stop
                if part["role"] == "omit":
                    if not part.get("reason"):
                        raise ValueError("Omission requires a reason")
                    continue
                chosen = copy.deepcopy(blocks[start:stop])
                for replacement in part.get("replacements", []):
                    offset = replacement["index"] - start
                    if (
                        not 0 <= offset < len(chosen)
                        or chosen[offset] != replacement["expected"]
                    ):
                        raise ValueError(
                            "Reviewed replacement no longer matches source"
                        )
                    chosen[offset] = replacement["block"]
                key = (
                    member
                    if len(review["pages"][member]) == 1
                    else f"{member}#part-{index + 1}"
                )
                node = chapter(key, part["title"], chosen, part["role"], start=start)
                if part["role"] == "extra":
                    book["extras"].append(book["chapters"].pop(node["member"]))
                    continue
                parent = part.get("parent")
                if parent:
                    if (
                        not book["sections"]
                        or book["sections"][-1].get("title") != parent
                    ):
                        book["sections"].append({"title": parent, "children": []})
                    book["sections"][-1]["children"].append(node)
                else:
                    book["sections"].append(node)
            if position != len(blocks):
                raise ValueError(f"Review leaves unaccounted blocks: {member}")
    else:
        leaves = []

        def flatten(nodes):
            for n in nodes:
                if "children" in n:
                    flatten(n["children"])
                elif n["member"] in pages:
                    leaves.append(n)

        flatten(toc)
        if not leaves:
            leaves = [
                {"member": m, "fragment": "", "title": inventory["titles"][m]}
                for m in pages
            ]
            toc = leaves
        listed = list(dict.fromkeys(n["member"] for n in leaves))
        if listed != list(pages):
            raise ValueError(
                "Navigation and spine disagree; use --inventory and --review to resolve coverage"
            )
        ranges = {}
        for i, n in enumerate(leaves):
            m, fragment = n["member"], n.get("fragment", "")
            if fragment and fragment not in inventory["anchors"][m]:
                raise ValueError(
                    f"Cannot locate fragment {m}#{fragment}; supply --review"
                )
            start = inventory["anchors"][m][fragment] if fragment else 0
            following = leaves[i + 1] if i + 1 < len(leaves) else {}
            end = (
                inventory["anchors"][m].get(following.get("fragment"), 0)
                if following.get("member") == m
                else len(pages[m])
            )
            if start >= end or (i == 0 or leaves[i - 1]["member"] != m) and start != 0:
                raise ValueError(
                    f"Ambiguous fragment boundaries in {m}; supply --review"
                )
            key = m + ("#" + fragment if fragment else "")
            if key in ranges:
                raise ValueError("Navigation repeats chapter")
            ranges[key] = (start, end)

        def convert(nodes):
            output = []
            for n in nodes:
                if "children" in n:
                    children = convert(n["children"])
                    if children:
                        output.append(
                            {
                                "title": n["title"],
                                "children": children,
                                **({"id": n["id"]} if n.get("id") else {}),
                            }
                        )
                elif n["member"] in pages:
                    key = n["member"] + (
                        "#" + n["fragment"] if n.get("fragment") else ""
                    )
                    a, b = ranges[key]
                    node = chapter(key, n["title"], pages[n["member"]][a:b], start=a)
                    if book["chapters"][node["member"]]["role"] == "extra":
                        book["extras"].append(book["chapters"].pop(node["member"]))
                    else:
                        output.append(node)
            return output

        book["sections"] = convert(toc)
    for ch in [*book["chapters"].values(), *book["extras"]]:
        for b in ch["blocks"]:
            for run in b["runs"]:
                overrides = (review or {}).get("link_overrides", {})
                if run.get("href") in overrides:
                    replacement = overrides[run["href"]]
                    if not replacement["reason"]:
                        raise ValueError("Link override requires source evidence")
                    if replacement["href"] is None:
                        run.pop("href")
                        run.pop("link_role", None)
                    else:
                        run["href"] = replacement["href"]
    resolve_book_references(book, inventory)
    evidence["reference_repairs"] = inventory.get("reference_repairs", [])
    cover_member = inventory["cover_member"]
    return InputBook(
        book,
        inventory["files"][cover_member] if cover_member else None,
        inventory["cover_mime"],
        evidence,
    )
