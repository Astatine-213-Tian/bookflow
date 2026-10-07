"""Notion-specific validation belongs at the destination, not in content loading."""

from __future__ import annotations

from notion_books import from_markdown, to_markdown

from src.content.blocks import content_signature


def read_content(markdown: str) -> list[dict]:
    """The shared codec preserves flat numbered prose and explicit references."""
    return from_markdown(markdown)


def validate_notion_content(book: dict) -> None:
    from src.content.contract import validate_book
    from src.notion.cms import chapter_entries

    validate_book(book)
    chapter_entries(book)
    chapters = [*book["chapters"].values(), *book.get("extras", [])]
    starts = set()
    for ch in chapters:
        first = next(
            (b for b in ch["blocks"] if "".join(r["text"] for r in b["runs"]).strip()),
            None,
        )
        if first and first.get("anchor"):
            starts.add(first["anchor"])
    for ch in chapters:
        local = {b["anchor"] for b in ch["blocks"] if b.get("anchor")}
        for b in ch["blocks"]:
            for r in b["runs"]:
                if r.get("href", "").startswith("#"):
                    target = r["href"][1:]
                    if r.get("link_role") and target not in local:
                        raise ValueError(
                            "Notion footnotes must belong to their referring chapter"
                        )
                    if not r.get("link_role") and target not in starts:
                        raise ValueError(
                            "Notion supports internal chapter-start links and paired footnotes; review this paragraph link before upload"
                        )
    for chapter in [*book["chapters"].values(), *book.get("extras", [])]:
        if chapter.get("related_works"):
            raise ValueError(
                "Notion cannot resolve content book IDs in related_works; use shared-extra duplicate review to link existing works"
            )
        blocks = chapter["blocks"]
        if any(b.get("variant") or b.get("language") for b in blocks):
            raise ValueError(
                "Notion cannot preserve bilingual language/variant annotations; export EPUB or TXT"
            )
        if content_signature(from_markdown(to_markdown(blocks))) != content_signature(
            blocks
        ):
            raise ValueError(f"Notion cannot preserve content: {chapter['title']}")
