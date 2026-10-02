"""Apply a reviewed official directory to an edition's existing chapter bodies."""

from __future__ import annotations

import re

from src.content.outline import ordered_members


class EditionOutlineError(ValueError):
    def __init__(self, differences: list[dict]) -> None:
        super().__init__(
            "Edition title differs from Jinjiang; review the proposed chapter aliases"
        )
        self.differences = differences


def prepare_extra_sections(book: dict) -> None:
    """Recognize an extra explicitly divided into consecutive standalone numbers."""
    for extra in book["extras"]:
        parts = [
            (index, "".join(r["text"] for r in block["runs"]).strip())
            for index, block in enumerate(extra["blocks"])
            if block["kind"] == "paragraph"
            and "".join(r["text"] for r in block["runs"]).strip().isdigit()
        ]
        if (
            len(parts) < 2
            or parts[0][0] != 0
            or [text for _, text in parts] != [str(n) for n in range(1, len(parts) + 1)]
        ):
            continue
        for index, _ in parts:
            extra["blocks"][index].update(kind="heading", level=3, alignment="center")


def apply_jjwxc_outline(
    book: dict, contents: dict, *, aliases: dict[str, str] | None = None
) -> dict:
    """Require chapter identities to agree; aliases explicitly record edition differences."""
    if aliases is not None and (
        not isinstance(aliases, dict)
        or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()
        )
    ):
        raise ValueError("Chapter aliases must be a JSON map of title strings")
    aliases = aliases or {}
    official = {}
    for volume in contents["volumes"]:
        for chapter in volume["chapters"]:
            number = chapter["number"]
            if number in official:
                raise ValueError("Official directory repeats a chapter number")
            official[number] = (volume["title"].replace("：", "·"), chapter["title"])
    sections = []
    differences = []
    unreviewed = []
    numbers = []
    for member in ordered_members(book["sections"]):
        chapter = book["chapters"][member]
        if chapter.get("role") == "intro":
            sections.append({"member": member})
            continue
        match = re.fullmatch(r"第(\d+)章\s*(.*)", chapter["title"])
        if not match or int(match[1]) not in official:
            raise ValueError(
                f"Chapter is absent from the official directory: {chapter['title']}"
            )
        number = int(match[1])
        numbers.append(number)
        parent, title = official[number]
        if match[2] != title:
            differences.append({"number": number, "local": match[2], "official": title})
            if aliases.get(chapter["title"]) != title:
                unreviewed.append(differences[-1] | {"local_title": chapter["title"]})
        if not parent:
            sections.append({"member": member})
        elif sections and sections[-1].get("title") == parent:
            sections[-1]["children"].append({"member": member})
        else:
            sections.append({"title": parent, "children": [{"member": member}]})
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("Edition chapter numbers are not continuous; review alignment")
    if unreviewed:
        raise EditionOutlineError(unreviewed)
    book["sections"] = sections
    # A recognized next-volume marker at a chapter tail is navigation, not prose.
    moved = []
    previous = None
    canonical = lambda value: re.sub(r"[\s·：:]", "", value)
    for node in sections:
        members = ordered_members([node])
        if previous and node.get("title"):
            blocks = book["chapters"][previous]["blocks"]
            if blocks and canonical(
                "".join(r["text"] for r in blocks[-1]["runs"])
            ) == canonical(node["title"]):
                moved.append({"member": previous, "title": node["title"]})
                blocks.pop()
        previous = members[-1]
    return {
        "title_differences": differences,
        "moved_trailing_volume_markers": moved,
        "aligned_main_chapters": len(numbers),
    }
