"""Select an input adapter; ambiguous images/text can be supplied as agent JSON."""

from __future__ import annotations

from pathlib import Path

from src.content.prepared import load_prepared_source
from src.inputs.epub import InputBook, read_epub_source
from src.inputs.text import read_txt_source


def read_input(
    path: Path, *, title: str = "", author: str = "", review: dict | None = None
) -> InputBook:
    suffix = path.suffix.lower()
    if suffix == ".json":
        source, cover, mime = load_prepared_source(path)
        return InputBook(source, cover, mime)
    if suffix == ".epub":
        return read_epub_source(path, review=review)
    if suffix == ".txt":
        return InputBook(read_txt_source(path, title=title, author=author))
    raise ValueError(
        "Input must be EPUB, TXT or content JSON; transcribe images / freestyle text with the book-management skill into the same schema"
    )
