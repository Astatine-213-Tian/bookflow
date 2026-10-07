"""Portable link validation and one explicit footnote representation."""

from __future__ import annotations

import copy
import re
from itertools import groupby
from urllib.parse import urlsplit

MARKER = re.compile(r"^(?:注?[①-⑳]|\[\d+\]|\d+[.、．])[ \t]*")
REFERENCE_MARKER = r"(?:\[\d+\]|[（(]\d+[）)]|注?[①-⑳])"
BACKLINK_LABEL = re.compile(r"(?:↩(?:\d+(?:\.\d+)?)?|返回|回到正文|back|return)", re.I)


def _linked_run_groups(runs: list[dict]):
    """Formatting boundaries inside one link do not create more references."""
    return groupby(runs, key=lambda run: (run.get("href"), run.get("link_role")))


def _reference_markers(runs: list[dict]) -> list[dict]:
    result = []
    for (href, role), group in _linked_run_groups(runs):
        linked = list(group)
        if role != "noteref":
            result.extend(linked)
            continue
        text = "".join(run["text"] for run in linked)
        # Adjacent complete markers are meaningful repeated references. A marker
        # split around styled digits, e.g. "[", "1", "]", is just one occurrence.
        labels = (
            re.findall(REFERENCE_MARKER, text)
            if re.fullmatch(rf"(?:{REFERENCE_MARKER})+", text)
            else [text]
        )
        result.extend(
            {"text": label, "styles": [], "href": href, "link_role": role}
            for label in labels
        )
    return result


def _note_body(group: list[dict]) -> list[dict]:
    runs = []
    for index, block in enumerate(group):
        if index:
            runs.append({"text": "\n\n", "styles": []})
        for (_, role), linked in _linked_run_groups(block["runs"]):
            linked = list(linked)
            if role == "backlink":
                label = "".join(run["text"] for run in linked)
                if BACKLINK_LABEL.fullmatch(label.strip()):
                    # Remove the old control and its separating whitespace. This
                    # also makes rebuilding an already prepared note idempotent.
                    while runs:
                        runs[-1]["text"] = runs[-1]["text"].rstrip()
                        if runs[-1]["text"]:
                            break
                        runs.pop()
                    continue
                # A backlink may contain real explanatory prose. Keep that text
                # and its styles, replacing only the obsolete link relationship.
                for run in linked:
                    run = copy.deepcopy(run)
                    run.pop("href", None)
                    run.pop("link_role", None)
                    runs.append(run)
            else:
                runs.extend(copy.deepcopy(linked))
    marker = MARKER.match("".join(run["text"] for run in runs))
    # Bare digits can be a year or quantity. Only explicit note markers are removed.
    remove = marker.end() if marker else 0
    for run in runs:
        cut = min(remove, len(run["text"]))
        run["text"] = run["text"][cut:]
        remove -= cut
    return [run for run in runs if run["text"]]


def canonicalize_footnotes(chapter: dict) -> dict:
    result = copy.deepcopy(chapter)
    blocks = result["blocks"]
    notes = {}
    for block in blocks:
        if block.get("footnote"):
            notes.setdefault(block["footnote"], []).append(block)
    if not notes:
        return result
    refs = {key: [] for key in notes}
    for block in blocks:
        if block.get("footnote"):
            continue
        block["runs"] = _reference_markers(block["runs"])
        for run in block["runs"]:
            if run.get("link_role") == "noteref":
                href = run.get("href") or ""
                key = href[1:]
                if not href.startswith("#") or key not in refs:
                    raise ValueError("Footnotes must be local to the referring chapter")
                if not block.get("anchor"):
                    raise ValueError("Footnote reference lacks a return anchor")
                refs[key].append((block, run))
    output = [block for block in blocks if not block.get("footnote")]
    # Always rebuild the complete pairing. A numbered prefix and one backlink
    # alone do not prove numbering, placement or return-link coverage is correct.
    for number, (key, group) in enumerate(notes.items(), 1):
        if not refs[key]:
            raise ValueError(f"Footnote has no body reference: {key}")
        for _, run in refs[key]:
            run.update(text=f"[{number}]", styles=[])
        runs = _note_body(group)
        prefix = {"text": f"[{number}] ", "styles": []}
        if runs and {k: v for k, v in runs[0].items() if k != "text"} == {"styles": []}:
            runs[0]["text"] = prefix["text"] + runs[0]["text"]
        else:
            runs.insert(0, prefix)
        for index, (body, _) in enumerate(refs[key], 1):
            runs.extend(
                [
                    {"text": " ", "styles": []},
                    {
                        "text": f"↩{number}"
                        + (f".{index}" if len(refs[key]) > 1 else ""),
                        "styles": [],
                        "href": "#" + body["anchor"],
                        "link_role": "backlink",
                    },
                ]
            )
        output.append({**group[0], "runs": runs, "anchor": key, "footnote": key})
    result["blocks"] = output
    return result


def validate_references(book: dict) -> None:
    chapters = [*book["chapters"].values(), *book.get("extras", [])]
    anchors = {}
    for ch in chapters:
        for b in ch["blocks"]:
            if b.get("anchor"):
                if b["anchor"] in anchors:
                    raise ValueError("Duplicate content anchor")
                anchors[b["anchor"]] = b
    for ch in chapters:
        for b in ch["blocks"]:
            if b.get("footnote") and b["footnote"] not in anchors:
                raise ValueError("Footnote lacks a destination anchor")
            for r in b["runs"]:
                href = r.get("href")
                if not href:
                    if r.get("link_role"):
                        raise ValueError("Reference lacks a hyperlink target")
                    continue
                u = urlsplit(href)
                if any(c in href for c in "\r\n\x00") or u.scheme not in {
                    "",
                    "https",
                    "http",
                    "mailto",
                }:
                    raise ValueError("Unsupported hyperlink scheme")
                if not u.scheme and not u.netloc:
                    if u.path or u.query or not u.fragment or u.fragment not in anchors:
                        raise ValueError(f"Unresolved internal hyperlink: {href}")
                if r.get("link_role") == "noteref" and not anchors.get(
                    u.fragment, {}
                ).get("footnote"):
                    raise ValueError("Note reference does not target a footnote")
