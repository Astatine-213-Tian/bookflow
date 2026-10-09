"""Import checkpoints and source identities around shared manuscript operations."""

from __future__ import annotations

from notion_books import chapter_targets, content_signature, localize_chapters

from src.runtime.files import write_json


def content_rows(book: dict) -> dict[tuple[str, str], dict]:
    return {
        **{("chapter", key): chapter for key, chapter in book["chapters"].items()},
        **{
            (
                ("extra", chapter["id"])
                if chapter.get("id")
                else ("extra-index", str(index))
            ): chapter
            for index, chapter in enumerate(book.get("extras", []))
        },
    }


def chapters(book: dict) -> list[dict]:
    return [
        {
            "title": row["title"],
            "blocks": row["blocks"],
            "page_id": row.get("page_id", ""),
        }
        for row in content_rows(book).values()
    ]


def checkpoint_page_ids(checkpoint: dict) -> dict[tuple[str, str], str]:
    return {
        key: row["page_id"]
        for key, row in content_rows(checkpoint).items()
        if row.get("page_id")
    }


def localize_chapter_links(book: dict, page_ids: dict[tuple[str, str], str]) -> None:
    rows = content_rows(book)
    localized = localize_chapters(
        [
            {
                "title": row["title"],
                "blocks": row["blocks"],
                "page_id": page_ids.get(key, ""),
            }
            for key, row in rows.items()
        ]
    )
    for row, chapter in zip(rows.values(), localized, strict=True):
        row["blocks"] = chapter["blocks"]


async def write_content(
    reader, item: dict, state, checkpoint: dict, targets: dict, *,
    expected: str = "", require_empty: bool = False,
) -> None:
    plan = item.get("content_write")
    if plan is None:
        plan = await reader.prepare_content(
            item["page_id"], item["blocks"], targets=targets, expected=expected
        )
        if require_empty and plan["before"] and not plan["done"]:
            raise ValueError(
                "New page contains editor content; reconcile without overwriting edits"
            )
        item["content_write"] = plan
        write_json(state, checkpoint)
    elif (
        plan["page_id"] != item["page_id"]
        or content_signature(plan["blocks"]) != content_signature(item["blocks"])
        or plan["targets"] != targets
    ):
        raise ValueError("Content changed since the write checkpoint was prepared")
    def save(next_plan):
        item["content_write"] = next_plan
        write_json(state, checkpoint)

    await reader.write_content(plan, checkpoint=save)


def targets(book: dict) -> dict[str, str]:
    return chapter_targets(chapters(book))
