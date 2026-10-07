from __future__ import annotations

from lxml import etree as ET
from notion_books import render_blocks as render_content

X = "http://www.w3.org/1999/xhtml"


def render_blocks(
    parent: ET._Element, blocks: list[dict], *, targets: dict[str, str] | None = None
) -> None:
    fragment = render_content(blocks, targets=targets)
    root = ET.fromstring(
        (
            f'<div xmlns="{X}" xmlns:epub="http://www.idpf.org/2007/ops">'
            + fragment
            + "</div>"
        ).encode()
    )
    for child in root:
        parent.append(child)
