"""XHTML-specific archive cleanup using the shared content text rules."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from src.content.normalization import (
    AUTHOR_NOTE_HEADING_RE,
    AUTHOR_NOTE_PARAGRAPH_RE,
    CHAPTER_LIKE_TITLE_RE,
    CHAPTER_NUMBER_PREFIX_RE,
    DECORATIVE_END_MARKER_RE,
    ENDING_TERMS,
    FULLWIDTH_ALPHANUMERIC,
    NormalizationReport,
    _mixed_boundary_positions,
    _normalize_fullwidth_alphanumeric,
    _normalize_plain_text,
    scan_content_issues,
)
from src.content.blocks import replace_run_text
from src.content.titles import normalize_volume_title


EPUB_OPS_NAMESPACE_DECL_RE = re.compile(
    r"xmlns:(?P<prefix>[A-Za-z_][\w.-]*)="
    r'(?P<quote>["\'])http://www\.idpf\.org/2007/ops(?P=quote)'
)


TOKEN_RE = re.compile(r"(<[^>]+>|&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);)")


PARAGRAPH_RE = re.compile(
    r"(?P<open><(?:[A-Za-z_][\w.-]*:)?p\b(?![^>]*?/\s*>)[^>]*>)"
    r"(?P<body>.*?)"
    r"(?P<close></(?:[A-Za-z_][\w.-]*:)?p>)",
    re.DOTALL,
)


STRUCTURAL_IDENTITY_RE = re.compile(
    r"\s(?:id|xml:id|name|href|data-book-anchor|data-book-footnote)\s*=",
    re.IGNORECASE,
)
PROTECTED_STRUCTURE_RE = re.compile(
    r"\sdata-variant\s*=|\bzh-translation\b|"
    r"\s(?:[\w.-]+:type|role)\s*=\s*([\"'])[^\"']*"
    r"\b(?:footnote|endnote|noteref|doc-footnote|doc-endnote|doc-noteref|doc-backlink)\b",
    re.IGNORECASE,
)
ORIGINAL_VARIANT_RE = re.compile(
    r"\sdata-variant\s*=\s*([\"'])original\1", re.IGNORECASE
)


BODY_TAGS = {"p"}


XHTML_TITLE_TAGS = {"title", "h1", "h2", "h3"}


NAV_TAGS = {"a", "span"}


NCX_TAGS = {"text"}


OPF_TAGS = {"title"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _surface_tags(member: str) -> set[str]:
    basename = Path(member).name
    if member.endswith(".xhtml"):
        return BODY_TAGS | XHTML_TITLE_TAGS
    if basename == "toc.ncx":
        return NCX_TAGS
    if basename == "content.opf":
        return OPF_TAGS
    return set()


def _tag_pattern(tags: Iterable[str]) -> re.Pattern[str]:
    alternatives = "|".join(sorted(map(re.escape, tags), key=len, reverse=True))
    return re.compile(
        rf"(<(?:[A-Za-z_][\w.-]*:)?(?:{alternatives})\b(?![^>]*?/\s*>)[^>]*>)"
        rf"(.*?)"
        rf"(</(?:[A-Za-z_][\w.-]*:)?(?:{alternatives})>)",
        re.DOTALL,
    )


def _normalize_nav_epub_namespace_prefix(
    text: str,
    *,
    member: str,
    report: NormalizationReport,
) -> str:
    match = EPUB_OPS_NAMESPACE_DECL_RE.search(text)
    if match is None or match.group("prefix") == "epub":
        return text

    prefix = match.group("prefix")
    normalized = EPUB_OPS_NAMESPACE_DECL_RE.sub(
        'xmlns:epub="http://www.idpf.org/2007/ops"',
        text,
        count=1,
    )
    qualified_name_re = re.compile(
        rf"(?P<boundary>[<\s/]){re.escape(prefix)}:(?=[A-Za-z_])"
    )
    normalized, qualified_names = qualified_name_re.subn(
        r"\g<boundary>epub:",
        normalized,
    )
    report.record_change(
        "nav_epub_namespace_prefix_normalized",
        member,
        1 + qualified_names,
        text,
        normalized,
    )
    return normalized


def _normalize_fragment(
    fragment: str,
    *,
    preserve_ordinals: bool,
    remove_han_spaces: bool,
    title_punctuation: bool,
    end_marker: bool,
    force_fanwai_title: bool,
    member: str,
    report: NormalizationReport,
) -> str:
    tokens = TOKEN_RE.split(fragment)
    for index, token in enumerate(tokens):
        if token.startswith("&"):
            decoded = html.unescape(token)
            if len(decoded) == 1 and ord(decoded) in FULLWIDTH_ALPHANUMERIC:
                tokens[index] = _normalize_fullwidth_alphanumeric(
                    decoded, member=member, report=report
                )
            continue
        if not token or token.startswith("<"):
            continue
        tokens[index] = _normalize_plain_text(
            token,
            preserve_ordinals=preserve_ordinals,
            remove_han_spaces=remove_han_spaces,
            title_punctuation=title_punctuation,
            end_marker=end_marker,
            force_fanwai_title=force_fanwai_title,
            member=member,
            report=report,
        )

    records: list[tuple[int, int, int, str] | None] = []
    for token_index, token in enumerate(tokens):
        if not token:
            continue
        if token.startswith("<"):
            tag = token[1:].lstrip("/").split(None, 1)[0].rstrip(">/").lower()
            if tag in {"br", "img", "hr"} and not token.startswith("</"):
                records.append(None)
            continue
        if token.startswith("&"):
            decoded = html.unescape(token)
            if len(decoded) == 1:
                records.append((token_index, 0, len(token), decoded))
            else:
                records.append(None)
            continue
        records.extend(
            (token_index, offset, offset + 1, char) for offset, char in enumerate(token)
        )
    visible = "".join(record[3] if record else "\n" for record in records)
    positions = _mixed_boundary_positions(visible, preserve_ordinals)
    insertions: dict[int, set[int]] = defaultdict(set)
    for position in positions:
        left = records[position]
        right = records[position + 1]
        if left is None or right is None or left[0] == right[0]:
            continue
        insertions[left[0]].add(left[2])
    cross_tag_count = sum(len(offsets) for offsets in insertions.values())
    if cross_tag_count:
        before = "".join(tokens)
        for token_index, offsets in insertions.items():
            token = tokens[token_index]
            for offset in sorted(offsets, reverse=True):
                token = token[:offset] + " " + token[offset:]
            tokens[token_index] = token
        report.record_change(
            "mixed_width_space_inserted",
            member,
            cross_tag_count,
            before,
            "".join(tokens),
        )
    return "".join(tokens)


def _visible_fragment_text(fragment: str) -> str:
    try:
        root = ET.fromstring(f"<root>{fragment}</root>")
    except ET.ParseError:
        return re.sub(r"<[^>]+>", "", fragment)
    return "".join(root.itertext())


def _author_note_heading_offset(fragment: str) -> int | None:
    """Find an author-note heading in a plain-text part of an XHTML fragment."""
    cursor = 0
    for token in TOKEN_RE.finditer(fragment):
        plain = fragment[cursor : token.start()]
        match = AUTHOR_NOTE_HEADING_RE.search(plain)
        if match is not None:
            return cursor + match.start()
        cursor = token.end()
    match = AUTHOR_NOTE_HEADING_RE.search(fragment[cursor:])
    if match is None:
        return None
    return cursor + match.start()


def _fragment_is_well_formed(fragment: str) -> bool:
    prefixes = {
        prefix
        for prefix in re.findall(r"</?([A-Za-z_][\w.-]*):", fragment)
        if prefix != "xml"
    }
    declarations = "".join(
        f' xmlns:{prefix}="urn:epub-normalizer:{prefix}"' for prefix in sorted(prefixes)
    )
    try:
        ET.fromstring(f"<root{declarations}>{fragment}</root>")
    except ET.ParseError:
        return False
    return True


def _center_paragraph_opening(opening: str) -> str:
    style_match = re.search(r"""(\sstyle\s*=\s*)(["'])(.*?)\2""", opening)
    additions = []
    existing = style_match.group(3) if style_match else ""
    if "text-align" not in existing:
        additions.append("text-align: center")
    if "text-indent" not in existing:
        additions.append("text-indent: 0")
    if not additions:
        return opening
    if style_match:
        separator = "" if not existing or existing.rstrip().endswith(";") else ";"
        style = existing + separator + " " + "; ".join(additions) + ";"
        return opening[: style_match.start(3)] + style + opening[style_match.end(3) :]
    style = "; ".join(additions) + ";"
    return opening[:-1] + f' style="{style}">'


def _normalize_structural_paragraphs(
    text: str,
    *,
    member: str,
    report: NormalizationReport,
) -> str:
    # Semantics may be declared on a containing aside/section, outside the
    # paragraph matched below. Keep aligned and note-bearing documents intact;
    # the JSON preparation path can safely reason about individual blocks.
    if PROTECTED_STRUCTURE_RE.search(text):
        return text
    while True:
        paragraphs = list(PARAGRAPH_RE.finditer(text))
        replacement: tuple[int, int, str, str, str] | None = None
        for paragraph in paragraphs:
            if STRUCTURAL_IDENTITY_RE.search(paragraph[0]):
                continue
            body = paragraph.group("body")
            marker_offset = _author_note_heading_offset(body)
            if marker_offset is None:
                continue
            before_body = body[:marker_offset].rstrip()
            author_note_body = body[marker_offset:].lstrip()
            if not _visible_fragment_text(before_body).strip():
                continue
            if not (
                _fragment_is_well_formed(before_body)
                and _fragment_is_well_formed(author_note_body)
            ):
                continue
            before = text[paragraph.start() : paragraph.end()]
            after = (
                paragraph.group("open")
                + before_body
                + paragraph.group("close")
                + "\n"
                + paragraph.group("open")
                + author_note_body
                + paragraph.group("close")
            )
            replacement = (
                paragraph.start(),
                paragraph.end(),
                after,
                "author_note_paragraph_break_inserted",
                before,
            )
            break
        if replacement is not None:
            start, end, after, kind, before = replacement
            report.record_change(kind, member, 1, before, after)
            text = text[:start] + after + text[end:]
            continue
        for first, second in zip(paragraphs, paragraphs[1:]):
            if text[first.end() : second.start()].strip():
                continue
            if (
                STRUCTURAL_IDENTITY_RE.search(first[0])
                or STRUCTURAL_IDENTITY_RE.search(second[0])
                or first.group("open") != second.group("open")
            ):
                continue
            first_text = _visible_fragment_text(first.group("body")).strip()
            second_text = _visible_fragment_text(second.group("body")).strip()
            if second_text in {"”", "’"}:
                before = text[first.start() : second.end()]
                after = (
                    first.group("open")
                    + first.group("body").rstrip()
                    + second_text
                    + first.group("close")
                )
                replacement = (
                    first.start(),
                    second.end(),
                    after,
                    "isolated_closing_quote_merged",
                    before,
                )
                break
            if (
                first_text.endswith(("，", ","))
                and second_text
                and AUTHOR_NOTE_PARAGRAPH_RE.match(second_text) is None
            ):
                before = text[first.start() : second.end()]
                after = (
                    first.group("open")
                    + first.group("body").rstrip()
                    + second.group("body").lstrip()
                    + first.group("close")
                )
                replacement = (
                    first.start(),
                    second.end(),
                    after,
                    "comma_paragraph_break_merged",
                    before,
                )
                break
        if replacement is None:
            return text
        start, end, after, kind, before = replacement
        report.record_change(kind, member, 1, before, after)
        text = text[:start] + after + text[end:]


def _grouped_fanwai_title_labels(members: dict[str, bytes]) -> set[str]:
    labels: set[str] = set()

    def record_label(value: str) -> None:
        match = CHAPTER_NUMBER_PREFIX_RE.match(value)
        if match is not None:
            if value[match.end() :].strip():
                labels.add(value)
        elif value:
            labels.add(value)

    for member, data in members.items():
        basename = Path(member).name
        if basename == "nav.xhtml":
            root = ET.fromstring(data)
            for item in root.iter():
                if _local_name(item.tag) != "li":
                    continue
                direct_labels = [
                    child
                    for child in list(item)
                    if _local_name(child.tag) in {"a", "span"}
                ]
                if not direct_labels:
                    continue
                parent_label = "".join(direct_labels[0].itertext()).strip()
                if parent_label != "番外":
                    continue
                for descendant in item.iter():
                    if (
                        descendant is direct_labels[0]
                        or _local_name(descendant.tag) != "a"
                    ):
                        continue
                    record_label("".join(descendant.itertext()).strip())
        elif basename == "toc.ncx":
            root = ET.fromstring(data)
            for point in root.iter():
                if _local_name(point.tag) != "navPoint":
                    continue
                direct_label = next(
                    (
                        child
                        for child in list(point)
                        if _local_name(child.tag) == "navLabel"
                    ),
                    None,
                )
                if direct_label is None:
                    continue
                parent_label = "".join(direct_label.itertext()).strip()
                if parent_label != "番外":
                    continue
                for descendant in point.iter():
                    if descendant is point or _local_name(descendant.tag) != "navPoint":
                        continue
                    child_label = next(
                        (
                            child
                            for child in list(descendant)
                            if _local_name(child.tag) == "navLabel"
                        ),
                        None,
                    )
                    if child_label is not None:
                        record_label("".join(child_label.itertext()).strip())
    return labels


def volume_title_labels(members: dict[str, bytes]) -> set[str]:
    """Use actual parent nodes, never volume-looking words in chapter prose."""
    labels = set()
    for member, data in members.items():
        name = Path(member).name
        if name not in {"nav.xhtml", "toc.ncx"}:
            continue
        root = ET.fromstring(data)
        for node in root.iter():
            tag = _local_name(node.tag)
            children = list(node)
            if (
                name == "nav.xhtml"
                and tag == "li"
                and any(_local_name(c.tag) == "ol" for c in children)
            ):
                label = next(
                    (c for c in children if _local_name(c.tag) in {"a", "span"}), None
                )
            elif (
                name == "toc.ncx"
                and tag == "navPoint"
                and any(_local_name(c.tag) == "navPoint" for c in children)
            ):
                label = next(
                    (c for c in children if _local_name(c.tag) == "navLabel"), None
                )
            else:
                continue
            if label is not None:
                labels.add("".join(label.itertext()).strip())
    return labels


def _normalize_volume_fragment(
    fragment: str, *, member: str, report: NormalizationReport
) -> str:
    tokens = TOKEN_RE.split(fragment)
    runs = [
        {"text": html.unescape(token), "styles": [], "token": i}
        for i, token in enumerate(tokens)
        if token and not token.startswith("<")
    ]
    normalized = normalize_volume_title(
        "".join(r["text"] for r in runs), member=member, report=report
    )
    replacements = defaultdict(str)
    for run in replace_run_text(runs, normalized):
        replacements[run["token"]] += html.escape(run["text"], quote=False)
    return "".join(
        token if token.startswith("<") else replacements[i]
        for i, token in enumerate(tokens)
    )


def normalize_member(
    member: str,
    data: bytes,
    report: NormalizationReport,
    *,
    grouped_fanwai_titles: set[str],
    volume_titles: set[str] | None = None,
) -> bytes:
    tags = _surface_tags(member)
    if not tags:
        return data
    text = data.decode("utf-8")
    if Path(member).name == "nav.xhtml":
        text = _normalize_nav_epub_namespace_prefix(
            text,
            member=member,
            report=report,
        )
    if member.endswith(".xhtml"):
        text = _normalize_structural_paragraphs(
            text,
            member=member,
            report=report,
        )

    def replace(match: re.Match[str]) -> str:
        opening, fragment, closing = match.groups()
        if ORIGINAL_VARIANT_RE.search(opening):
            return match[0]
        opening_tag = re.match(
            r"<(?:[A-Za-z_][\w.-]*:)?([A-Za-z0-9]+)",
            opening,
        )
        tag = opening_tag.group(1).lower() if opening_tag else ""
        preserve_ordinals = tag in XHTML_TITLE_TAGS | NAV_TAGS | NCX_TAGS | OPF_TAGS
        visible = _visible_fragment_text(fragment).strip()
        if (
            preserve_ordinals
            and Path(member).name != "content.opf"
            and visible in (volume_titles or set())
        ):
            return (
                opening
                + _normalize_volume_fragment(fragment, member=member, report=report)
                + closing
            )
        force_fanwai_title = visible in grouped_fanwai_titles
        title_punctuation = bool(
            preserve_ordinals
            and (
                force_fanwai_title
                or "番外" in visible
                or CHAPTER_LIKE_TITLE_RE.match(visible)
            )
        )
        marker_match = (
            DECORATIVE_END_MARKER_RE.fullmatch(visible) if tag == "p" else None
        )
        end_marker = bool(
            marker_match
            and any(
                marker_match.group("label").strip().endswith(term)
                for term in ENDING_TERMS
            )
        )
        if end_marker:
            centered_opening = _center_paragraph_opening(opening)
            report.record_change(
                "decorative_end_marker_centered",
                member,
                int(centered_opening != opening),
                opening,
                centered_opening,
            )
            opening = centered_opening
        remove_han_spaces = tag == "p" and Path(member).name != "intro.xhtml"
        return (
            opening
            + _normalize_fragment(
                fragment,
                preserve_ordinals=preserve_ordinals,
                remove_han_spaces=remove_han_spaces,
                title_punctuation=title_punctuation,
                end_marker=end_marker,
                force_fanwai_title=force_fanwai_title,
                member=member,
                report=report,
            )
            + closing
        )

    if Path(member).name == "nav.xhtml":
        pattern = _tag_pattern(NAV_TAGS | XHTML_TITLE_TAGS)
    else:
        pattern = _tag_pattern(tags)
    normalized = pattern.sub(replace, text)
    ET.fromstring(normalized.encode("utf-8"))
    report.xml_members_checked += 1
    return normalized.encode("utf-8")


def _scan_member_issues(
    member: str,
    data: bytes,
    report: NormalizationReport,
) -> None:
    if not member.endswith((".xhtml", ".ncx", ".opf")):
        return
    root = ET.fromstring(data)
    report.xml_members_checked += 1
    # Intro pages contain metadata, tag lists, source links, and intentionally
    # loose formatting rather than continuous prose. Deterministic cleanup has
    # already run, but prose-quality review findings from intro.xhtml are noise.
    if Path(member).name == "intro.xhtml":
        return
    paragraphs = [
        "".join(element.itertext())
        for element in root.iter()
        if _local_name(element.tag) == "p"
    ]
    headings = [
        "".join(element.itertext())
        for element in root.iter()
        if _local_name(element.tag) in XHTML_TITLE_TAGS
    ]
    has_prose = member.endswith(".xhtml")
    if not has_prose:
        headings = [text for text in root.itertext() if text and text.strip()]
    scan_content_issues(member, paragraphs, headings, report, has_prose=has_prose)
