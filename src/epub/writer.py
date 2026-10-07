"""Create a new EPUB from prepared content, without interpreting its prose."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from ebooklib import epub
from lxml import etree as ET

from src.content.outline import ordered_members
from src.content.styles import CSS
from src.epub.archive import X, install_archive, validate_archive, validate_navigation
from src.epub.xhtml import render_blocks
from src.runtime.files import digest


def create_book(
    book: dict,
    output: Path,
    *,
    cover: bytes | None = None,
    cover_name: str = "cover.jpg",
) -> None:
    metadata = book["metadata"]
    package = epub.EpubBook()
    package.set_identifier(book["identifier"])
    package.set_title(metadata["title"])
    package.set_language(metadata["language"] or "zh-CN")
    for index, creator in enumerate(metadata.get("creators") or [metadata["creator"]]):
        package.add_author(creator, uid=f"creator-{index + 1}")
    for key in ("date", "source", "description"):
        if metadata.get(key):
            package.add_metadata("DC", key, metadata[key])
    for subject in metadata.get("subjects", []):
        package.add_metadata("DC", "subject", subject)
    if metadata.get("series"):
        package.add_metadata(
            None,
            "meta",
            metadata["series"],
            {"property": "belongs-to-collection", "id": "series"},
        )
        package.add_metadata(
            None,
            "meta",
            "series",
            {"property": "collection-type", "refines": "#series"},
        )
        if metadata.get("series_position") not in (None, ""):
            package.add_metadata(
                None,
                "meta",
                str(metadata["series_position"]),
                {"property": "group-position", "refines": "#series"},
            )
    css = epub.EpubItem(
        uid="style_main", file_name="style/main.css", media_type="text/css", content=CSS
    )
    package.add_item(css)
    if cover:
        package.set_cover(cover_name, cover, create_page=False)
    items = {}
    for index, (member, chapter) in enumerate(book["chapters"].items(), 1):
        root = ET.Element(f"{{{X}}}html", nsmap={None: X})
        head = ET.SubElement(root, f"{{{X}}}head")
        ET.SubElement(head, f"{{{X}}}title").text = chapter["title"]
        ET.SubElement(
            head,
            f"{{{X}}}link",
            rel="stylesheet",
            href="style/main.css",
            type="text/css",
        )
        container = ET.SubElement(root, f"{{{X}}}body")
        # EbookLib rebuilds <body>; keep source identities on its content wrapper.
        body = ET.SubElement(container, f"{{{X}}}div")
        body.set("data-book-chapter-id", member)
        body.set("data-book-role", chapter.get("role", "chapter"))
        if chapter.get("role") == "intro":
            body.set("class", "intro")
        ET.SubElement(body, f"{{{X}}}h2").text = chapter["title"]
        render_blocks(body, chapter["blocks"])
        item = epub.EpubHtml(
            title=chapter["title"],
            file_name=f"chapter_{index:04d}.xhtml",
            content=ET.tostring(root),
            lang=metadata["language"] or "zh-CN",
        )
        item.add_item(css)
        package.add_item(item)
        items[member] = item

    def toc(nodes):
        return tuple(
            (
                epub.Section(
                    n["title"], href=items[ordered_members(n["children"])[0]].file_name
                ),
                toc(n["children"]),
            )
            if "children" in n
            else items[n["member"]]
            for n in nodes
        )

    package.toc = toc(book["sections"])
    package.spine = ["nav"] + [items[m] for m in ordered_members(book["sections"])]
    package.add_item(epub.EpubNcx())
    nav_root = ET.Element(
        f"{{{X}}}html", nsmap={None: X, "epub": "http://www.idpf.org/2007/ops"}
    )
    nav_head = ET.SubElement(nav_root, f"{{{X}}}head")
    ET.SubElement(nav_head, f"{{{X}}}title").text = metadata["title"]
    nav_body = ET.SubElement(nav_root, f"{{{X}}}body")
    nav = ET.SubElement(nav_body, f"{{{X}}}nav")
    nav.set("{http://www.idpf.org/2007/ops}type", "toc")

    def navigation(parent, nodes):
        ol = ET.SubElement(parent, f"{{{X}}}ol")
        for node in nodes:
            li = ET.SubElement(ol, f"{{{X}}}li")
            if "children" in node:
                if node.get("id"):
                    li.set("data-volume-id", node["id"])
                first = ordered_members(node["children"])[0]
                ET.SubElement(li, f"{{{X}}}a", href=items[first].file_name).text = node[
                    "title"
                ]
                navigation(li, node["children"])
            else:
                member = node["member"]
                ET.SubElement(
                    li, f"{{{X}}}a", href=items[member].file_name
                ).text = book["chapters"][member]["title"]

    navigation(nav, book["sections"])
    nav_item = epub.EpubItem(
        uid="nav",
        file_name="nav.xhtml",
        media_type="application/xhtml+xml",
        content=ET.tostring(nav_root, encoding="utf-8", xml_declaration=True),
    )
    nav_item.properties = ["nav"]
    package.add_item(nav_item)
    output.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output), package, {})
    validate_archive(output)
    validate_navigation(output, "EPUB/nav.xhtml", "EPUB/toc.ncx", "EPUB/content.opf")


def export_local(
    source: dict,
    output: Path,
    *,
    cover: bytes | None = None,
    cover_mime: str = "image/jpeg",
    prevent_overwrite: bool = True,
) -> Path:
    """Render the prepared crawl, including extras, without any Notion access."""
    if output.exists() and prevent_overwrite:
        raise ValueError("Output EPUB exists; choose another path or use --overwrite")
    original = digest(output.read_bytes()) if output.exists() else None
    book = copy.deepcopy(source)
    extras = []
    for index, story in enumerate(book.get("extras", []), 1):
        member = story.get("id") or f"extra-{index}"
        if member in book["chapters"]:
            raise ValueError(f"Duplicate extra ID: {member}")
        book["chapters"][member] = {**story, "role": "extra"}
        extras.append({"member": member})
    if extras:
        book["sections"].append({"title": "番外", "children": extras})
    suffix = {"image/png": "png", "image/gif": "gif", "image/webp": "webp"}.get(
        cover_mime, "jpg"
    )
    with tempfile.TemporaryDirectory(prefix="book-export-") as temporary:
        candidate = Path(temporary) / "book.epub"
        create_book(book, candidate, cover=cover, cover_name=f"cover.{suffix}")
        install_archive(candidate, output, original)
    return output
