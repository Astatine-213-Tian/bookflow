"""Collect through the registry and persist the shared JSON input to later tasks."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.content.contract import validate_book
from src.content.prepared import save_source
from src.crawler.models import CrawlOptions, DownloadedEdition
from src.crawler.registry import find_parser
from src.inputs.crawl import extract_crawl
from src.inputs.epub import read_epub_source
from src.runtime.files import write_json


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
    options = options or CrawlOptions()
    collected = find_parser(target, provider).crawl(target, options)
    evidence = {}
    if isinstance(collected, DownloadedEdition):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.epub"
            path.write_bytes(collected.epub_bytes)
            edition = read_epub_source(path)
            book, cover, mime = edition.source, edition.cover, edition.cover_mime
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
        cover, mime = collected.cover_bytes, collected.cover_mime
        evidence = collected.evidence or {}
    validate_book(book)
    save_source(book, output / "source.json", cover, mime)
    write_json(output / "evidence.json", evidence)
    return output / "source.json"
