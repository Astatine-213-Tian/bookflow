"""Reviewed casing of common names, without spelling guesses or token rewrites."""

from __future__ import annotations

import re

PRODUCT_NAMES = (
    "iPhone",
    "iPad",
    "iPod",
    "iOS",
    "macOS",
    "iMac",
    "Mac",
    "MacBook",
    "MacBook Air",
    "MacBook Pro",
    "AirPods",
    "Apple Watch",
    "Apple TV",
    "Android",
    "Windows",
    "Microsoft",
    "Google",
    "Bluetooth",
    "Wi-Fi",
    "GitHub",
    "GitLab",
    "YouTube",
    "Facebook",
    "Instagram",
    "WhatsApp",
    "WeChat",
    "TikTok",
    "LinkedIn",
    "WordPress",
    "PowerPoint",
    "JavaScript",
    "TypeScript",
    "ChatGPT",
    "OpenAI",
    "PlayStation",
    "Xbox",
)
ABBREVIATIONS = (
    "QQ",
    "MSN",
    "DVD",
    "CD",
    "USB",
    "HDMI",
    "CPU",
    "GPU",
    "PDF",
    "KTV",
    "VIP",
    "MV",
    "MP3",
    "MP4",
    "CEO",
    "CFO",
    "CTO",
    "COO",
    "GPS",
    "SIM",
    "DIY",
)
CANONICAL_TERMS = {term.casefold(): term for term in (*PRODUCT_NAMES, *ABBREVIATIONS)}
NUMBERED_PRODUCTS = {
    term.casefold()
    for term in ("iPhone", "iPad", "iPod", "iOS", "macOS", "Windows", "PlayStation")
}
TERM_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<term>"
    + "|".join(
        re.escape(term) for term in sorted(CANONICAL_TERMS, key=len, reverse=True)
    )
    + r")(?P<number>[0-9]*)(?![A-Za-z0-9_])",
    re.IGNORECASE | re.ASCII,
)
PROTECTED_RE = re.compile(
    r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`"
    r"|(?:[a-z][a-z0-9+.-]*://|www\.)[^\s<>\"'，。！？；：、（）《》【】]+"
    r"|[a-z0-9_.+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"|(?:[a-z0-9_-]+\.)+[a-z0-9_-]+(?:[/\\][^\s<>\"'，。！？；：、（）《》【】]+)?"
    r"|(?:[a-z]:[/\\]|\.{0,2}/|~/)[^\s<>\"'，。！？；：、（）《》【】]+"
    r"|[@#][a-z0-9_]+",
    re.IGNORECASE | re.ASCII,
)


def code_term_ranges(runs: list[dict]) -> list[tuple[int, int]]:
    ranges = []
    offset = 0
    for run in runs:
        end = offset + len(run["text"])
        if "code" in run.get("styles", []) and end > offset:
            ranges.append((offset, end))
        offset = end
    return ranges


def normalize_english_terms(
    text: str, *, protected_ranges: list[tuple[int, int]] | None = None
) -> tuple[str, int]:
    """Normalize exact case-insensitive names in prose, retaining protected spans."""
    count = 0

    def prose(value: str, offset: int) -> str:
        def replace(match: re.Match) -> str:
            nonlocal count
            start, stop = offset + match.start(), offset + match.end()
            if (start and re.fullmatch(r"[A-Za-z0-9_]", text[start - 1])) or (
                stop < len(text) and re.fullmatch(r"[A-Za-z0-9_]", text[stop])
            ):
                return match[0]
            key = match["term"].casefold()
            if match["number"] and key not in NUMBERED_PRODUCTS:
                return match[0]
            # The network acronym is not the computer's product name.
            if key == "mac" and re.match(
                r"\s*(?:地址|位址|address\b)", value[match.end() :], re.IGNORECASE
            ):
                return match[0]
            after = CANONICAL_TERMS[key] + match["number"]
            count += after != match[0]
            return after

        return TERM_RE.sub(replace, value)

    spans = [(m.start(), m.end()) for m in PROTECTED_RE.finditer(text)]
    spans.extend(protected_ranges or [])
    merged = []
    for start, stop in sorted(spans):
        if not 0 <= start < stop <= len(text):
            raise ValueError("Term protection range is outside its text")
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(stop, merged[-1][1]))
        else:
            merged.append((start, stop))
    pieces = []
    end = 0
    for start, stop in merged:
        pieces.extend((prose(text[end:start], end), text[start:stop]))
        end = stop
    pieces.append(prose(text[end:], end))
    return "".join(pieces), count
