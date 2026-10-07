"""Validate prepared imports using the shared Notion manuscript contract."""

from notion_books import validate_chapters

from src.content.contract import validate_book
from src.notion.content import chapters


def validate_notion_content(book: dict) -> None:
    from src.notion.cms import chapter_entries

    validate_book(book)
    chapter_entries(book)
    for chapter in [*book["chapters"].values(), *book.get("extras", [])]:
        if chapter.get("related_works"):
            raise ValueError(
                "Resolve shared-extra relations through duplicate review before upload"
            )
    validate_chapters(chapters(book))
