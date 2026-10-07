"""Notion-specific validation belongs at the destination, not in content loading."""

from __future__ import annotations

from notion_books import from_markdown, to_markdown

from src.content.blocks import content_signature


def validate_notion_content(book: dict) -> None:
    from src.content.contract import validate_book
    from src.notion.cms import chapter_entries

    validate_book(book)
    chapter_entries(book)
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
