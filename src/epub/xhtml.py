from __future__ import annotations

import re

from lxml import etree as ET

X = "http://www.w3.org/1999/xhtml"


def render_blocks(
    parent: ET._Element, blocks: list[dict], *, targets: dict[str, str] | None = None
) -> None:
    for block in blocks:
        tag = {
            "paragraph": "p",
            "heading": "h" + str(block.get("level", 3)),
            "quote": "blockquote",
            "divider": "hr",
        }[block["kind"]]
        if block.get("footnote"):
            tag = "aside"
        el = ET.SubElement(parent, f"{{{X}}}{tag}", **block.get("attributes", {}))
        if block.get("anchor"):
            el.set("id", block["anchor"])
            el.set("data-book-anchor", block["anchor"])
        if block.get("footnote"):
            el.set("{http://www.idpf.org/2007/ops}type", "footnote")
            el.set("role", "doc-footnote")
            el.set("data-book-footnote", block["footnote"])
        if block.get("language"):
            el.set("{http://www.w3.org/XML/1998/namespace}lang", block["language"])
        if block.get("variant"):
            el.set("data-variant", block["variant"])
            if block["variant"] == "translation":
                el.set("class", "zh-translation")
        # Content H3 has one global size, independent of alignment and template.
        if tag == "h3":
            style = re.sub(
                r"(?:^|;)\s*font-size\s*:[^;]*(?:;|$)",
                ";",
                el.get("style", ""),
                flags=re.I,
            ).strip("; ")
            el.set("style", (style + "; " if style else "") + "font-size: 1.1em;")
        alignment = block.get("alignment", "left" if tag == "h3" else None)
        if alignment:
            if alignment not in {"left", "center", "right", "justify"}:
                raise ValueError("Unsupported paragraph alignment")
            style = el.get("style", "").rstrip("; ")
            if style:
                style += "; "
            style += f"text-align: {alignment};"
            if alignment in {"center", "right"}:
                style += " text-indent: 0;"
            el.set("style", style)
        for run in block["runs"]:
            target = el
            if run.get("href"):
                href = run["href"]
                if targets is not None and href.startswith("#"):
                    if href[1:] not in targets:
                        raise ValueError(f"Unresolved EPUB hyperlink: {href}")
                    href = targets[href[1:]]
                target = ET.SubElement(target, f"{{{X}}}a", href=href)
                if run.get("link_role") == "noteref":
                    target.set("{http://www.idpf.org/2007/ops}type", "noteref")
                    target.set("role", "doc-noteref")
                elif run.get("link_role") == "backlink":
                    target.set("role", "doc-backlink")
            for style in run["styles"]:
                name = {
                    "bold": "strong",
                    "italic": "em",
                    "underline": "u",
                    "strikethrough": "s",
                    "code": "code",
                }[style]
                target = ET.SubElement(target, f"{{{X}}}{name}")
            for index, text in enumerate(run["text"].split("\n")):
                if index:
                    ET.SubElement(target, f"{{{X}}}br")
                if len(target):
                    target[-1].tail = (target[-1].tail or "") + text
                else:
                    target.text = (target.text or "") + text
