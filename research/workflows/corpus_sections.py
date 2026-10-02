"""Remove non-core sections from research copies, leaving source TXT untouched."""
from __future__ import annotations

import hashlib
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup

from src.dataset.text import clean_text_line


SECTION_CLEANING_VERSION = "core_narrative_sections_v1"
NUMBERS = "0-9零一二三四五六七八九十百千万两〇壹贰叁肆伍陆柒捌玖拾"
NUMBERED_HEADING_RE = re.compile(rf"^(?:第[{NUMBERS}]+[章节卷部篇回]|卷[{NUMBERS}]+)")
SPECIAL_HEADING_RE = re.compile(r"^(?:正文|楔子|引子|序章|尾声|终章|終章)(?:$|[\s·：:（(])")
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"


def member_anchors(data: bytes) -> tuple[list[str], list[str]]:
    try:
        doc = ET.fromstring(data)
    except ET.ParseError:
        soup = BeautifulSoup(data, "html.parser")
        return (
            [clean_text_line(node.get_text()) for node in soup.find_all(["h1", "h2", "h3"])],
            [clean_text_line(node.get_text()) for node in soup.find_all("p")],
        )
    return (
        [clean_text_line("".join(node.itertext())) for node in doc.iter()
         if node.tag.rsplit("}", 1)[-1] in {"h1", "h2", "h3"}],
        [clean_text_line("".join(node.itertext())) for node in doc.iter()
         if node.tag.rsplit("}", 1)[-1] == "p"],
    )


def excluded_kind(heading: str) -> str:
    """Only call on a known heading, never on arbitrary narrative paragraphs."""
    if re.search(r"番外|外传|外傳|特典", heading):
        return "extra"
    if re.search(r"后记|後記", heading):
        return "afterword"
    if re.search(r"简介|簡介|文案", heading):
        return "synopsis"
    return ""


def plain_heading(line: str) -> bool:
    if len(line) > 90:
        return False
    if NUMBERED_HEADING_RE.match(line) or SPECIAL_HEADING_RE.match(line):
        return True
    value = line.strip("【】[]（）() \t")
    return bool(re.match(
        r"^(?:简介|簡介|内容简介|作品简介|文案|后记|後記|番外|特典)"
        r"(?:$|[\s·：:（(一二三四五六七八九十0-9]|卷)", value
    ))


def epub_boundaries(lines: list[str], epub_path: Path | None) -> tuple[dict[int, dict[str, str]], dict[str, Any]]:
    """Align TOC ancestry to unchanged TXT lines; do not replace prose from EPUB.

    Local EPUBs can have been repaired since export. Unique heading or opening
    paragraph matches ignoring punctuation/space retain the TXT's order/body.
    Unmatched entries are reported, never guessed by chapter number or position.
    """
    if epub_path is None or not epub_path.is_file():
        return {}, {"mode": "txt_headings", "unmatched": []}
    occurrences: dict[str, list[int]] = defaultdict(list)
    def anchor_key(value: str) -> str:
        return re.sub(r"[\W_]+", "", value)

    for index, line in enumerate(lines):
        if line:
            occurrences[anchor_key(line)].append(index)
    boundaries: dict[int, dict[str, str]] = {}
    unmatched: list[dict[str, Any]] = []
    with zipfile.ZipFile(epub_path) as archive:
        ncx_files = [name for name in archive.namelist() if name.endswith(".ncx")]
        if not ncx_files:
            return {}, {"mode": "txt_headings", "unmatched": [], "reason": "no_ncx"}
        ncx_path = ncx_files[0]
        root = ET.fromstring(archive.read(ncx_path))
        members: dict[str, dict[str, Any]] = {}

        def visit(point: ET.Element, inherited: str = "") -> None:
            label = point.findtext(f"{NCX}navLabel/{NCX}text", default="").strip()
            kind = inherited or excluded_kind(label)
            content = point.find(f"{NCX}content")
            if content is not None:
                href = unquote(content.get("src", "").split("#", 1)[0])
                member = posixpath.normpath(posixpath.join(posixpath.dirname(ncx_path), href))
                item = members.setdefault(member, {"labels": [], "kind": ""})
                item["labels"].append(label)
                if kind:
                    item["kind"] = kind
            for child in point.findall(f"{NCX}navPoint"):
                visit(child, kind)

        for point in root.findall(f"{NCX}navMap/{NCX}navPoint"):
            visit(point)
        for member, item in members.items():
            if member not in archive.namelist():
                unmatched.append({"member": member, "kind": item["kind"], "reason": "missing_member"})
                continue
            headings, opening = member_anchors(archive.read(member))
            # Prefer the XHTML heading over the TOC label (which may be a volume).
            candidates = headings[:1] + list(reversed(item["labels"]))
            matches = [occurrences[anchor_key(value)][0] for value in candidates
                       if anchor_key(value) and len(occurrences.get(anchor_key(value), [])) == 1]
            start = matches[0] if matches else None
            if start is None:
                for value in opening[:20]:
                    key = anchor_key(value)
                    if len(key) < 10 or len(occurrences.get(key, [])) != 1:
                        continue
                    anchor = occurrences[key][0]
                    # An exported XHTML section starts after a blank separator.
                    start = anchor
                    while start > 0 and lines[start - 1] and anchor - start < 12:
                        start -= 1
                    if start > 0 and lines[start - 1]:
                        # Some older exports omit the blank before a section.
                        # Recover its opening using consecutive source content,
                        # rather than walking backwards into the previous story.
                        opening_keys = {anchor_key(value) for value in opening[:20] if len(anchor_key(value)) >= 10}
                        window_keys = {anchor_key(value) for value in lines[anchor:anchor + 24]}
                        if len(window_keys & opening_keys) < 2:
                            start = None
                            continue
                        start = anchor
                        first_keys = {anchor_key(value) for value in opening[:20] if len(anchor_key(value)) >= 4}
                        while start > 0 and anchor - start < 20 and anchor_key(lines[start - 1]) in first_keys:
                            start -= 1
                        tails = [anchor_key(re.split(r"[·：:]", value)[-1]) for value in candidates]
                        while start > 0 and anchor - start < 24:
                            previous = lines[start - 1]
                            if len(previous) > 90 or not (
                                plain_heading(previous)
                                or (item["kind"] and excluded_kind(previous) == item["kind"])
                                or any(len(tail) >= 5 and anchor_key(previous).endswith(tail) for tail in tails)
                            ):
                                break
                            start -= 1
                    break
            starts = [start] if start is not None else []
            if not starts:
                # Repeated exports can contain the same afterword/extra twice.
                # Match both copies only with two distinct opening paragraphs.
                opening_keys = {anchor_key(value) for value in opening[:20] if len(anchor_key(value)) >= 10}
                candidate_starts = set()
                for key in opening_keys:
                    for anchor in occurrences.get(key, []):
                        candidate = anchor
                        while candidate > 0 and lines[candidate - 1] and anchor - candidate < 12:
                            candidate -= 1
                        if candidate > 0 and lines[candidate - 1]:
                            continue
                        window_keys = {anchor_key(value) for value in lines[candidate:candidate + 24]}
                        if len(window_keys & opening_keys) >= 2:
                            candidate_starts.add(candidate)
                starts = sorted(candidate_starts)
            if not starts:
                overlaps = sum(bool(occurrences.get(anchor_key(value))) for value in opening if len(anchor_key(value)) >= 10)
                unmatched.append({"member": member, "kind": item["kind"], "reason": "no_unique_raw_anchor", "raw_paragraph_overlap_count": overlaps})
                continue
            for start in starts:
                # Both the source TXT label and TOC ancestry can identify an extra.
                raw_kind = excluded_kind(lines[start]) if plain_heading(lines[start]) else ""
                boundary = {"kind": item["kind"] or raw_kind, "member": member, "heading": lines[start]}
                existing = boundaries.get(start)
                if existing and existing["kind"] != boundary["kind"]:
                    raise ValueError(f"Conflicting EPUB section alignment at TXT line {start + 1}: {epub_path}")
                boundaries[start] = boundary
    return boundaries, {
        "mode": "epub_toc_and_txt_headings",
        "anchor_matching": "unique_alphanumeric_text_ignoring_punctuation_and_whitespace",
        "source_epub_sha256": hashlib.sha256(epub_path.read_bytes()).hexdigest(),
        "matched_section_count": len(boundaries), "unmatched": unmatched,
    }


def remove_noncore_sections(lines: list[str], *, epub_path: Path | None = None) -> tuple[list[str], dict[str, Any]]:
    boundaries, provenance = epub_boundaries(lines, epub_path)
    first_main = min((index for index, entry in boundaries.items() if not entry["kind"]), default=len(lines))
    first_main = min(first_main, next((index for index, line in enumerate(lines) if NUMBERED_HEADING_RE.match(line)), len(lines)))
    for index, line in enumerate(lines):
        if index not in boundaries and plain_heading(line):
            kind = excluded_kind(line)
            # Fictional screens, blurbs and dialogue can contain these words.
            # Once the story starts, a synopsis needs structural TOC evidence.
            if kind == "synopsis" and index > first_main:
                continue
            if kind and not NUMBERED_HEADING_RE.match(line) and index > 0 and lines[index - 1]:
                bare = line.strip("【】[]（）() ：:")
                annotated_afterword = bool(re.fullmatch(r"(?:后记|後記)[（(][^。！？\n]{1,30}[）)]", line))
                if bare not in {"简介", "簡介", "文案", "后记", "後記", "番外"} and not annotated_afterword:
                    continue
            boundaries[index] = {"kind": kind, "member": "", "heading": line}
    if provenance["mode"] == "txt_headings":
        # Some TXT-only exports number the bonus chapters without labelling them.
        # Require an explicit end-of-main-story notice announcing extras nearby.
        for index, line in enumerate(lines):
            if not re.match(r"^(?:作者有话要说|[—-]{2,})", line):
                continue
            if not re.search(r"正文.{0,12}(?:完结|完了|结束)", line):
                continue
            if "番外" not in "\n".join(lines[index:index + 20]):
                continue
            boundaries[index] = {"kind": "extra", "member": "", "heading": "explicit_main_story_end_notice"}
            for position, entry in boundaries.items():
                if position > index:
                    entry["kind"] = entry["kind"] or "extra"
            provenance["terminal_extras_notice_line"] = index + 1
            break
    # TOC membership wins over an unlabelled chapter inside an extra volume.
    positions = sorted(boundaries)
    output = list(lines)
    removed = []
    for offset, start in enumerate(positions):
        entry = boundaries[start]
        if not entry["kind"]:
            continue
        end = positions[offset + 1] if offset + 1 < len(positions) else len(lines)
        text = "\n".join(lines[start:end])
        removed.append({
            **entry, "start_line": start + 1, "end_line": end,
            "cjk_count": len(re.findall(r"[\u4e00-\u9fff]", text)),
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        })
        output[start:end] = [""] * (end - start)
    return output, {
        "section_cleaning": SECTION_CLEANING_VERSION,
        "section_line_coordinates": "normalized_raw_lines_1_based_inclusive",
        "section_boundary_provenance": provenance,
        "removed_sections": removed,
        "removed_section_cjk_count": sum(item["cjk_count"] for item in removed),
    }
