"""Synthetic shared content for public pipeline tests."""

from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.content.contract import metadata_defaults
from src.content.prepared import save_source
from src.inputs.crawl import extract_crawl
from src.workflows.prepare import prepare_book


def isolated_workdir(test: TestCase) -> Path:
    directory = Path(test.enterContext(TemporaryDirectory()))
    test.enterContext(chdir(directory))
    return directory


def paragraph(text, styles=None):
    return {"kind": "paragraph", "runs": [{"text": text, "styles": styles or []}]}


def prepared_crawl(**kwargs):
    return prepare_book(extract_crawl(**kwargs))[0]


def write_source(
    directory: Path,
    paragraphs,
    *,
    key="01",
    title="Test Book",
    author="Test Author",
    chapter_title="Chapter 1",
    source=None,
    cover=None,
):
    chapter = {
        "title": chapter_title,
        "role": "chapter",
        "blocks": [paragraph(p) for p in paragraphs],
    }
    if source:
        chapter["source"] = source
    book = {
        "version": 3,
        "identifier": "fixture",
        "metadata": metadata_defaults(
            {"title": title, "creator": author, "language": "en"}
        ),
        "sections": [{"member": key}],
        "chapters": {key: chapter},
        "extras": [],
    }
    save_source(book, directory / "source.json", cover, "image/png")
    return book
