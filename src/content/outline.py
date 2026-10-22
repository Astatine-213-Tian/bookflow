from __future__ import annotations


def ordered_members(sections: list[dict], depth: int = 1) -> list[str]:
    if depth > 3:
        raise ValueError("Book outline supports at most three levels")
    result = []
    for node in sections:
        if "children" in node:
            if not node["children"]:
                raise ValueError("Outline contains an empty heading")
            result.extend(ordered_members(node["children"], depth + 1))
        else:
            result.append(node["member"])
    return result


FANWAI_GROUP = "番外"


def _fanwai(title: str) -> bool:
    return "番外" in title.replace("番外卷", "")


def group_fanwai(book: dict) -> list[str]:
    """Move 番外 chapters outside any 番外 heading into one trailing 番外 group.

    Sources such as Jinjiang list extras inside the last main volume or after the
    final chapter; readers find them under one 番外 heading. A chapter already
    under a heading naming 番外 or 番外卷 stays put. Returns the moved members.
    """
    moved: list[dict] = []

    def visit(nodes: list[dict], grouped: bool) -> list[dict]:
        kept = []
        for node in nodes:
            if "children" in node:
                children = visit(node["children"], grouped or "番外" in node["title"])
                if children:
                    kept.append({**node, "children": children})
                continue
            chapter = book["chapters"][node["member"]]
            if (
                not grouped
                and chapter.get("role", "chapter") == "chapter"
                and _fanwai(chapter["title"])
            ):
                moved.append(node)
            else:
                kept.append(node)
        return kept

    sections = visit(book["sections"], False)
    if not moved:
        return []
    last = sections[-1] if sections else {}
    if "children" in last and "番外" in last["title"]:
        last["children"].extend(moved)
    else:
        sections.append({"title": FANWAI_GROUP, "children": moved})
    book["sections"] = sections
    return [node["member"] for node in moved]
