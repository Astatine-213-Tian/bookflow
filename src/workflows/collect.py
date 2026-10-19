"""Collect through the registry and persist the shared JSON input to later tasks."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.content.contract import validate_book
from src.content.prepared import save_source
from src.crawler.models import CrawledBook, CrawlOptions, DownloadedEdition
from src.crawler.registry import ParserSpec, find_parser
from src.inputs.crawl import extract_crawl
from src.runtime.files import write_json


@dataclass(frozen=True)
class Collected:
    book: dict
    cover: bytes | None = None
    cover_mime: str = "image/jpeg"
    evidence: dict = field(default_factory=dict)


def extract_collected(
    collected: CrawledBook | DownloadedEdition,
    options: CrawlOptions | None = None,
) -> Collected:
    """Convert a provider result into the shared book JSON without preparation."""
    options = options or CrawlOptions()
    if isinstance(collected, DownloadedEdition):
        from src.inputs.epub import read_epub_source

        with tempfile.TemporaryDirectory(prefix="book-input-") as temp:
            path = Path(temp) / "download.epub"
            path.write_bytes(collected.epub_bytes)
            edition = read_epub_source(path)
        result = Collected(edition.source, edition.cover, edition.cover_mime)
    else:
        book = extract_crawl(
            title=options.title or collected.title,
            author=options.author or collected.author,
            volumes=collected.volumes,
            source_url=collected.source_url,
            intro_paragraphs=collected.intro_paragraphs,
            intro_html=collected.intro_html,
            language=options.language or collected.language,
        )
        result = Collected(
            book,
            collected.cover_bytes,
            collected.cover_mime,
            collected.evidence or {},
        )
    validate_book(result.book)
    return result


def collect(
    target: str,
    parser: ParserSpec,
    options: CrawlOptions | None = None,
) -> Collected:
    options = options or CrawlOptions()
    return extract_collected(parser.crawl(target, options), options)


def crawl_options(
    config: dict[str, Any],
    *,
    delay: float = 0.4,
    concurrency: int = 2,
    headless: bool = False,
    title: str = "",
    author: str = "",
    language: str = "",
    include_comments: bool = False,
    extra_post_ids: tuple[str, ...] = (),
) -> CrawlOptions:
    source = config.get("source") or {}
    return CrawlOptions(
        delay=delay,
        concurrency=max(1, concurrency),
        headless=headless,
        title=title or config.get("title", ""),
        author=author or config.get("author", ""),
        language=language or source.get("language", ""),
        include_comments=include_comments or bool(source.get("comments", False)),
        extra_post_ids=extra_post_ids or tuple(source.get("extra_post_ids", [])),
    )


def collect_source(
    target: str,
    output: Path,
    *,
    provider: str | None = None,
    options: CrawlOptions | None = None,
) -> Path:
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Collection directory is not empty; choose a fresh output directory"
        )
    collected = collect(target, find_parser(target, provider), options)
    save_source(
        collected.book, output / "source.json", collected.cover, collected.cover_mime
    )
    write_json(output / "evidence.json", collected.evidence)
    return output / "source.json"
