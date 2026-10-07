from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chapter:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    html_blocks: list[str] | None = None
    source_id: str = ""
    source_url: str = ""
    published_at: str = ""
    role: str = "chapter"


@dataclass
class Volume:
    title: str
    chapters: list[Chapter] = field(default_factory=list)
