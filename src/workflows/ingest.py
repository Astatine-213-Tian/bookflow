"""Collect once, normalize once, then write to explicitly selected destinations."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from src.crawler.models import CrawledBook, CrawlOptions, DownloadedEdition
from src.crawler.registry import ParserSpec
from src.dataset.text import write_prepared_txt
from src.inputs.crawl import extract_crawl
from src.runtime.paths import (
    dataset_txt_output_path,
    resolve_output_path,
    resolve_txt_output_path,
)
from src.workflows.prepare import prepare_book, prepare_file, save_prepared
from src.content.changes import content_hash
from src.runtime.files import digest


@dataclass(frozen=True)
class OutputOptions:
    output: Path | None = None
    txt_output: Path | None = None
    output_formats: tuple[str, ...] = ()
    dataset_root: Path | None = None
    prevent_overwrite: bool = True
    enrich_metadata: bool = False


@dataclass(frozen=True)
class IngestResult:
    epub_path: Path | None = None
    txt_path: Path | None = None
    notion_state: Path | None = None
    source_path: Path | None = None


def requested_formats(options: OutputOptions) -> tuple[str, ...]:
    formats: list[str] = []
    chosen = options.output_formats or tuple(
        name
        for name, path in (("epub", options.output), ("txt", options.txt_output))
        if path is not None
    )
    if not chosen:
        raise ValueError(
            "Choose an output with --mode/--output-format epub, notion or txt; "
            "repeat the option to combine formats, or provide -o/--txt-output"
        )
    for output_format in chosen:
        normalized = output_format.strip().lower()
        if normalized == "both":
            normalized_formats = ("epub", "txt")
        else:
            normalized_formats = (normalized,)
        for item in normalized_formats:
            if item not in {"notion", "epub", "txt"}:
                raise ValueError(f"unsupported output format: {output_format}")
            if item not in formats:
                formats.append(item)
    if options.output is not None and "epub" not in formats:
        raise ValueError("--output requires the epub format")
    if options.txt_output is not None and "txt" not in formats:
        raise ValueError("--txt-output requires the txt format")
    return tuple(formats)


def resolve_requested_txt_output(
    options: OutputOptions,
    *,
    title: str,
    author: str,
) -> Path:
    if options.txt_output is not None:
        return resolve_txt_output_path(options.txt_output, title, author)
    if options.dataset_root:
        return dataset_txt_output_path(
            options.dataset_root,
            title=title,
            author=author,
            time_area="",
            genre="",
        )
    return resolve_txt_output_path(options.txt_output, title, author)


def write_book(
    book: dict,
    options: OutputOptions,
    *,
    cover: bytes | None = None,
    cover_mime: str = "image/jpeg",
    cover_url: str | None = None,
    input_path: Path | None = None,
) -> IngestResult:
    from src.content.contract import validate_book
    from src.epub.writer import export_local

    validate_book(book)
    formats = requested_formats(options)
    metadata = book["metadata"]
    epub_path = (
        resolve_output_path(options.output, metadata["title"], metadata["creator"])
        if "epub" in formats
        else None
    )
    txt_path = (
        resolve_requested_txt_output(
            options, title=metadata["title"], author=metadata["creator"]
        )
        if "txt" in formats
        else None
    )
    for path in (epub_path, txt_path):
        if path and input_path and path.resolve() == input_path.resolve():
            raise ValueError("Choose a different output path; input is preserved")
        if path and options.prevent_overwrite and path.exists():
            raise ValueError(f"Output exists: {path}")
    if "notion" in formats:
        from src.notion.capabilities import validate_notion_content

        validate_notion_content(book)
    if epub_path:
        export_local(
            book,
            epub_path,
            cover=cover,
            cover_mime=cover_mime,
            prevent_overwrite=options.prevent_overwrite,
        )
    if txt_path:
        write_prepared_txt(book, txt_path)
    notion_state = None
    if "notion" in formats:
        from src.notion.upload import upload_source

        notion_state = upload_source(
            book, cover_bytes=cover if not cover_url else None, cover_url=cover_url
        )
    return IngestResult(epub_path, txt_path, notion_state)


def write_outputs(book: CrawledBook, options: OutputOptions) -> IngestResult:
    requested_formats(options)
    source = extract_crawl(
        title=book.title,
        author=book.author,
        volumes=book.volumes,
        source_url=book.source_url,
        intro_paragraphs=book.intro_paragraphs,
        intro_html=book.intro_html,
        language=book.language,
    )
    return prepare_and_write(
        source,
        options,
        cover=book.cover_bytes,
        cover_mime=book.cover_mime,
        evidence=book.evidence,
    )


def prepare_and_write(
    source: dict,
    options: OutputOptions,
    *,
    cover: bytes | None = None,
    cover_mime: str = "image/jpeg",
    evidence: dict | None = None,
) -> IngestResult:
    prepared, reports = prepare_book(source, enrich=options.enrich_metadata)
    fingerprint = content_hash(
        {
            "book": prepared,
            "reports": reports,
            "evidence": evidence,
            "cover": digest(cover) if cover else None,
        }
    )
    directory = Path("generated/ingest") / fingerprint[:16]
    source_path = save_prepared(
        prepared, directory, reports, cover, cover_mime, evidence=evidence
    )
    return replace(
        write_book(prepared, options, cover=cover, cover_mime=cover_mime),
        source_path=source_path,
    )


def ingest_local(
    path: Path,
    options: OutputOptions,
    *,
    run_dir: Path | None = None,
    title: str = "",
    author: str = "",
    review: dict | None = None,
    chapter_aliases: dict | None = None,
    chapter_layout: dict | None = None,
    use_jjwxc_outline: bool = False,
    cover_url: str | None = None,
) -> IngestResult:
    from src.runtime.files import digest

    requested_formats(options)
    directory = run_dir or Path("generated/ingest") / digest(path.read_bytes())[:16]
    book, cover, mime = prepare_file(
        path,
        directory,
        title=title,
        author=author,
        review=review,
        chapter_aliases=chapter_aliases,
        chapter_layout=chapter_layout,
        use_jjwxc_outline=use_jjwxc_outline,
        enrich=options.enrich_metadata,
    )
    return replace(
        write_book(
            book,
            options,
            cover=cover,
            cover_mime=mime,
            cover_url=cover_url,
            input_path=path,
        ),
        source_path=directory / "source.json",
    )


def ingest(
    target: str,
    *,
    parser: ParserSpec,
    crawl_options: CrawlOptions,
    output_options: OutputOptions,
) -> IngestResult:
    requested_formats(output_options)
    collected = parser.crawl(target, crawl_options)
    if isinstance(collected, DownloadedEdition):
        from src.inputs.epub import read_epub_source

        with tempfile.TemporaryDirectory(prefix="book-input-") as temporary:
            path = Path(temporary) / "download.epub"
            path.write_bytes(collected.epub_bytes)
            edition = read_epub_source(path)
            return prepare_and_write(
                edition.source,
                output_options,
                cover=edition.cover,
                cover_mime=edition.cover_mime,
            )
    return write_outputs(collected, output_options)
