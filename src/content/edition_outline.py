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


def apply_edition_layout(book: dict, layout: dict) -> list[dict]:
    """Apply reviewed chapter splits/classification without silently losing blocks."""
    if not isinstance(layout, dict) or set(layout) - set(book["chapters"]):
        raise ValueError("Edition layout must map existing chapter members")
    chapters = dict(book["chapters"])
    replacements, extras, report = {}, [], []
    for member in ordered_members(book["sections"]):
        if member not in layout:
            continue
        original = book["chapters"][member]
        decision = layout[member]
        if (
            not isinstance(decision, dict)
            or decision.get("expected_title") != original["title"]
        ):
            raise ValueError(f"Edition layout title changed: {member}")
        parts = decision.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Edition layout requires reviewed parts: {member}")
        position = 0
        nodes = []
        chapters.pop(member)
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                raise ValueError(f"Invalid edition layout part: {member}")
            start, stop = part.get("start"), part.get("stop")
            role, title = part.get("role"), part.get("title")
            if (
                type(start) is not int
                or type(stop) is not int
                or start != position
                or not start < stop <= len(original["blocks"])
                or role not in {"chapter", "afterword", "extra", "omit"}
                or not isinstance(title, str)
                or not title.strip()
                or (role == "omit" and not part.get("reason"))
            ):
                raise ValueError(
                    f"Invalid or incomplete edition layout coverage: {member}"
                )
            position = stop
            item = original | {
                "title": title,
                "role": role,
                "blocks": original["blocks"][start:stop],
            }
            if role == "extra":
                item["id"] = f"{member}-extra-{index + 1}"
                extras.append(item)
            elif role != "omit":
                key = member if index == 0 else member + f"-part-{index + 1}"
                if key in chapters:
                    raise ValueError(f"Edition layout member collision: {key}")
                chapters[key] = item
                nodes.append({"member": key})
            report.append(
                {"member": member, "original_title": original["title"], **part}
            )
        if position != len(original["blocks"]):
            raise ValueError(f"Edition layout leaves unreviewed blocks: {member}")
        replacements[member] = nodes

    def rebuild(nodes: list[dict]) -> list[dict]:
        result = []
        for node in nodes:
            if "member" in node:
                result.extend(replacements.get(node["member"], [node]))
            else:
                children = rebuild(node["children"])
                if children:
                    result.append(node | {"children": children})
        return result

    sections = rebuild(book["sections"])
    if not chapters:
        raise ValueError("Edition layout must retain main content")
    book.update(chapters=chapters, sections=sections, extras=extras + book["extras"])
    return report


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
        if chapter.get("role") in {"intro", "afterword"}:
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
        if chapter["title"] != title and match[2] != title:
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
