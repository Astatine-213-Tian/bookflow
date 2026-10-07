"""Collection contracts, independent of the chosen output destination."""

from __future__ import annotations

from dataclasses import dataclass

from src.content.models import Volume


@dataclass(frozen=True)
class CrawlOptions:
    delay: float | None = None
    request_interval: float = 0.0
    headless: bool = False
    concurrency: int | None = None
    title: str = ""
    author: str = ""
    language: str = ""
    include_comments: bool = False
    extra_post_ids: tuple[str, ...] = ()


@dataclass
class CrawledBook:
    title: str
    author: str
    volumes: list[Volume]
    source_url: str
    cover_bytes: bytes | None = None
    cover_mime: str = "image/jpeg"
    intro_paragraphs: list[str] | None = None
    intro_html: str = ""
    language: str = "zh-CN"
    evidence: dict | None = None


@dataclass(frozen=True)
class DownloadedEdition:
    title: str
    author: str
    source_url: str
    epub_bytes: bytes
