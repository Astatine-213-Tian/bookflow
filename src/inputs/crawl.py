"""Convert provider content to the same JSON emitted by file and agent inputs."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from src.content.contract import metadata_defaults
from src.content.html import escape_text
from src.content.models import Volume
from src.inputs.html import read_html_blocks


def extract_crawl(
    *,
    title: str,
    author: str,
    volumes: list[Volume],
    source_url: str,
    intro_paragraphs: list[str] | None = None,
    intro_html: str = "",
    language: str = "zh-CN",
) -> dict:
    book = {
        "version": 3,
        "identifier": str(uuid5(NAMESPACE_URL, source_url)),
        "source_format": "crawl",
        "metadata": metadata_defaults(
            {
                "title": title,
                "creator": author,
                "language": language,
                "source": source_url,
            }
        ),
        "sections": [],
        "chapters": {},
        "extras": [],
    }

    def chapter(name: str, body: str, role: str = "chapter") -> dict:
        document = f'<html xmlns="http://www.w3.org/1999/xhtml"><head/><body>{body}</body></html>'.encode()
        blocks = read_html_blocks(document, "content.xhtml", {})
        return {"title": name, "blocks": blocks, "role": role}

    intro = (
        "".join(f"<p>{escape_text(p)}</p>" for p in intro_paragraphs)
        if intro_paragraphs is not None
        else intro_html
    )
    if intro:
        key = "intro"
        book["chapters"][key] = chapter("简介", intro, "intro")
        book["sections"].append({"member": key})
        book["metadata"]["description"] = "\n".join(
            "".join(r["text"] for r in b["runs"])
            for b in book["chapters"][key]["blocks"]
        )
    for vi, volume in enumerate(volumes, 1):
        children = []
        for ci, item in enumerate(volume.chapters, 1):
            key = item.source_id or f"chapter-{vi}-{ci}"
            if key in book["chapters"]:
                raise ValueError(f"Duplicate source chapter ID: {key}")
            body = (
                "\n".join(item.html_blocks)
                if item.html_blocks is not None
                else "".join(f"<p>{escape_text(p)}</p>" for p in item.paragraphs)
            )
            value = chapter(item.title, body)
            if item.source_id or item.source_url:
                value["source"] = {
                    "id": item.source_id,
                    "url": item.source_url,
                    "published_at": item.published_at,
                }
            # Explicit provider classification; a volume named 番外 remains a volume.
            if item.role == "extra":
                value["id"] = key
                value["role"] = "extra"
                book["extras"].append(value)
            else:
                value["role"] = item.role
                book["chapters"][key] = value
                children.append({"member": key})
        if children:
            if volume.title and (len(volumes) > 1 or volume.title != "正文"):
                book["sections"].append(
                    {"id": f"volume-{vi}", "title": volume.title, "children": children}
                )
            else:
                book["sections"].extend(children)
    return book
