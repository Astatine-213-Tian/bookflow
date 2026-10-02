"""Read an existing edition into the shared editable content contract."""

from __future__ import annotations

import posixpath
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZipFile

from lxml import etree as ET
from notion_books import from_markdown, to_markdown

from src.content.blocks import content_signature
from src.content.formatting import prepare_blocks
from src.content.outline import ordered_members
from src.content.xhtml import read_xhtml
from src.epub.metadata import _find_opf_member, _package_metadata
from src.runtime.files import digest


@dataclass(frozen=True)
class LocalEdition:
    source: dict
    cover: bytes | None
    cover_mime: str


def read_epub_source(path: Path) -> LocalEdition:
    """Preserve spine, hierarchy, paragraphs and repeats; reject unsupported content."""
    with ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError("EPUB contains a corrupt ZIP member")
        opf_member = _find_opf_member(archive)
        files = {name: archive.read(name) for name in archive.namelist()}
    package = ET.fromstring(files[opf_member])
    base = posixpath.dirname(opf_member)

    def resolve(parent: str, href: str) -> str:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError(f"Unsupported chapter navigation target: {href}")
        return posixpath.normpath(posixpath.join(parent, unquote(parsed.path)))

    manifest = {
        item.get("id"): (resolve(base, item.get("href", "")), item)
        for item in package.findall("{*}manifest/{*}item")
    }
    navs = [
        (name, item)
        for name, item in manifest.values()
        if "nav" in item.get("properties", "").split()
    ]
    if len(navs) != 1:
        raise ValueError(
            "EPUB requires one navigation document; run book-normalize first"
        )
    nav_name = navs[0][0]
    nav_root = ET.fromstring(files[nav_name])
    tocs = nav_root.xpath(
        '//*[local-name()="nav" and @epub:type="toc"]',
        namespaces={"epub": "http://www.idpf.org/2007/ops"},
    )
    if len(tocs) != 1:
        raise ValueError("EPUB requires one explicit table of contents")

    def outline(ol) -> list[dict]:
        result = []
        for li in ol.findall("{*}li"):
            labels = [n for n in li if ET.QName(n).localname in {"a", "span"}]
            if len(labels) != 1:
                raise ValueError("Ambiguous EPUB navigation label")
            label = labels[0]
            nested = li.find("{*}ol")
            if nested is not None:
                children = outline(nested)
                if (
                    label.get("href")
                    and resolve(posixpath.dirname(nav_name), label.get("href"))
                    != ordered_members(children)[0]
                ):
                    raise ValueError(
                        "Linked parent has independent content; review the outline"
                    )
                result.append(
                    {"title": "".join(label.itertext()).strip(), "children": children}
                )
            else:
                result.append(
                    {
                        "member": resolve(
                            posixpath.dirname(nav_name), label.get("href", "")
                        )
                    }
                )
        return result

    toc_list = tocs[0].find("{*}ol")
    if toc_list is None:
        raise ValueError("EPUB table of contents has no chapter list")
    sections = outline(toc_list)
    members = ordered_members(sections)
    if len(members) != len(set(members)):
        raise ValueError("EPUB navigation repeats a chapter document")
    spine = []
    metadata = asdict(_package_metadata(files[opf_member]))
    for ref in package.findall("{*}spine/{*}itemref"):
        member, item = manifest[ref.get("idref")]
        if member == nav_name:
            continue
        if posixpath.basename(member) in {
            "cover.xhtml",
            "cover.html",
            "titlepage.xhtml",
            "title-page.xhtml",
        }:
            body = ET.fromstring(files[member]).find("{*}body")
            text = "".join(body.itertext()).strip() if body is not None else ""
            if text and text not in {metadata["title"], metadata["author"]}:
                raise ValueError(
                    f"Cover/title page contains text requiring review: {member}"
                )
            continue
        if item.get("media-type") != "application/xhtml+xml":
            raise ValueError(f"Unsupported reading-order content: {member}")
        spine.append(member)
    if members != spine:
        raise ValueError(
            "EPUB navigation and reading order disagree; repair before importing"
        )
    metadata["creator"] = metadata.pop("author")
    metadata["subjects"] = list(metadata["subjects"])
    chapters = {}
    for member in members:
        data = files[member]
        title = ET.fromstring(data).findtext("{*}head/{*}title") or ""
        blocks = prepare_blocks(data, member, files, read_xhtml(data, title=title))
        if content_signature(from_markdown(to_markdown(blocks))) != content_signature(
            blocks
        ):
            raise ValueError(f"Markdown cannot preserve chapter content: {member}")
        chapters[member] = {
            "title": title,
            "blocks": blocks,
            "role": "intro" if title == "简介" else "chapter",
        }
    extras = []
    main_sections = []
    for node in sections:
        if node.get("title") == "番外":
            extras.extend(chapters.pop(member) for member in ordered_members([node]))
        else:
            main_sections.append(node)
    # Flat editions often have trailing extras without a parent group.
    while main_sections and "member" in main_sections[-1]:
        member = main_sections[-1]["member"]
        if (
            "番外" not in chapters[member]["title"]
            or "番外卷" in chapters[member]["title"]
        ):
            break
        main_sections.pop()
        extras.insert(0, chapters.pop(member))
    if not chapters:
        raise ValueError("EPUB contains no main chapters")
    source = {
        "version": 2,
        "identifier": str(
            uuid5(NAMESPACE_URL, "local-epub:" + digest(path.read_bytes()))
        ),
        "source_format": "epub",
        "metadata": metadata,
        "sections": main_sections,
        "chapters": chapters,
        "extras": extras,
    }
    covers = [
        (member, item)
        for member, item in manifest.values()
        if "cover-image" in item.get("properties", "").split()
    ]
    if not covers:
        ids = package.xpath('//*[local-name()="meta" and @name="cover"]/@content')
        covers = [manifest[id] for id in ids if id in manifest]
    if len(covers) > 1:
        raise ValueError("EPUB declares multiple cover images")
    cover, mime = (
        (files[covers[0][0]], covers[0][1].get("media-type", ""))
        if covers
        else (None, "")
    )
    return LocalEdition(source, cover, mime)
