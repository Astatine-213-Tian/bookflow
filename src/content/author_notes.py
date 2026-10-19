"""Plain-text author notes, excluding site widgets and image-only material."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.content.blocks import block_text
from src.content.normalization import AUTHOR_NOTE_HEADING_RE, normalized_end_marker
from src.content.normalize import normalize_text

IMAGE_CAPTION = re.compile(
    r"插画|插图|贴图|图床|图挂|图裂|下图|上图|这[张幅]图|这幅画|看图|图见|图片|图图|[上下]面这张|[这那]张是|有图|把图|配图"
)
TICKET_LINE = re.compile(
    r"(?:投[了出].{0,15}(?:地雷|手榴弹|火箭炮|深水鱼雷)|灌溉.{0,10}营养液|霸王票排行|营养液排行)"
)
ENTRY_ONLY = re.compile(
    r"(?:点我|点击(?:这里|进入|直达|查看)?|传送门|戳我|戳这里|https?://\S+)[~～!！。\s]*$"
)


def plain_note(markup: str) -> dict:
    soup = BeautifulSoup(markup, "html.parser")
    removed = []
    image_reference_texts = set()
    # Old notes sometimes put an image URL inside angle brackets. HTML repair
    # turns it into a tag that contains the following caption, so keep that text
    # for semantic review instead of treating it as independent prose.
    for node in soup.find_all(["http:", "https:"]):
        if any(re.search(r"\.(?:jpe?g|png|gif|webp)$", key, re.I) for key in node.attrs):
            image_reference_texts.update(
                value.strip() for value in node.get_text("\n").splitlines() if value.strip()
            )
            removed.append({"kind": "malformed_image_element", "tag": node.name})
            node.unwrap()
    # Recommendation links can be rendered as buttons; their visible titles
    # have the same value as anchor labels. Never execute the click handler.
    for node in soup.select('input[type="button"][onclick], button[onclick]'):
        if re.search(r"\bwindow\.open\(\s*['\"]https?://", node["onclick"]):
            label = node.get("value", "") if node.name == "input" else node.get_text()
            node.replace_with(f"\n{label}\n")
    for node in soup.select(
        "script,style,img,iframe,object,form,input,button,#danmu_main,.danmu_main,.marquee"
    ):
        removed.append({"kind": "non_text_element", "tag": node.name})
        node.decompose()
    for node in soup.select("br"):
        node.replace_with("\n")
    for node in soup.select("p,div,li"):
        node.insert_before("\n")
        node.insert_after("\n")
    lines = []
    review = []
    for value in soup.get_text().splitlines():
        line = value.strip()
        if not line:
            continue
        if re.fullmatch(r"作者有话(?:要)?说[：:]?", line):
            continue
        if TICKET_LINE.search(line) or ENTRY_ONLY.fullmatch(line):
            removed.append({"kind": "site_widget_or_empty_entry", "text": line})
            continue
        # Captions need a semantic decision; a word like 插图 can occur in prose.
        if IMAGE_CAPTION.search(line) or line in image_reference_texts:
            review.append(len(lines))
        # Anchor labels survive, but links and bare URLs are never exported.
        line = re.sub(r"https?://\S+", "", line).strip()
        if line:
            lines.append(line)
    return {"lines": lines, "removed": removed, "image_reference_lines": review}


def note_blocks(lines: list[str]) -> list[dict]:
    if not lines:
        return []
    return [
        {"kind": "divider", "runs": []},
        {"kind": "paragraph", "runs": [{"text": "作者有话说：", "styles": []}]},
        *[
            {
                "kind": "paragraph",
                "runs": [{"text": normalize_text(text), "styles": []}],
            }
            for text in lines
        ],
    ]


def author_note_ranges(blocks: list[dict]) -> list[tuple[int, int]]:
    """Explicit author-note spans, stopping before an ending or appended edition."""
    result = []
    start = None
    for i, block in enumerate(blocks):
        text = block_text(block).strip()
        heading = (
            block["kind"] == "paragraph"
            and not block.get("variant")
            and not block.get("footnote")
            and AUTHOR_NOTE_HEADING_RE.match(text)
        )
        boundary = (
            block["kind"] == "divider"
            or block["kind"].startswith("heading")
            or normalized_end_marker(text) is not None
            or re.fullmatch(r"(?:【.+】|\[.+\])", text)
        )
        if start is not None and (heading or boundary):
            result.append((start, i))
            start = None
        if heading:
            start = i
    if start is not None:
        result.append((start, len(blocks)))
    return result
