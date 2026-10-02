"""Existing local editions enter the same prepared-source and output workflow."""

from __future__ import annotations

import copy
import difflib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET

from src.content.edition_outline import (
    EditionOutlineError,
    apply_jjwxc_outline,
    prepare_extra_sections,
)
from src.content.prepared import load_prepared_source
from src.content.text_source import read_txt_source
from src.dataset.text import write_prepared_txt
from src.epub.maintenance import normalize_and_review_epub, normalize_new_epub
from src.epub.normalize import normalize_epub
from src.epub.source import LocalEdition, read_epub_source
from src.epub.writer import export_local
from src.runtime.files import digest, write_json
from src.workflows.ingest import (
    IngestResult,
    OutputOptions,
    requested_formats,
    resolve_requested_txt_output,
)


def read_edition(path: Path, *, title: str = "", author: str = "") -> LocalEdition:
    if path.suffix.lower() == ".epub":
        return read_epub_source(path)
    if path.suffix.lower() == ".txt":
        return LocalEdition(read_txt_source(path, title=title, author=author), None, "")
    raise ValueError("Local editions must be EPUB or TXT")


def prepare_local(
    path: Path,
    run_dir: Path,
    *,
    title: str = "",
    author: str = "",
    chapter_aliases: dict[str, str] | None = None,
    use_jjwxc_outline: bool = True,
) -> tuple[dict, bytes | None, str]:
    """Normalize a copy, validate all surfaces, and persist the reusable source."""
    signature = {
        "path": str(path.resolve()),
        "sha256": digest(path.read_bytes()),
        "title": title,
        "author": author,
        "chapter_aliases": chapter_aliases or {},
        "use_jjwxc_outline": use_jjwxc_outline,
    }
    manifest = run_dir / "input.json"
    source_path = run_dir / "source.json"
    if source_path.exists():
        if not manifest.exists() or json.loads(manifest.read_text()) != signature:
            raise ValueError("Local preparation inputs changed; use a fresh --run-dir")
        return load_prepared_source(source_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        previous_input = json.loads(manifest.read_text())
        if any(previous_input.get(key) != signature[key] for key in ("path", "sha256")):
            raise ValueError("Preparation directory belongs to different input bytes")
    write_json(manifest, signature)
    candidate = run_dir / "candidate.epub"
    if path.suffix.lower() == ".epub":
        shutil.copy2(path, candidate)
    else:
        edition = read_edition(path, title=title, author=author)
        export_local(edition.source, candidate, prevent_overwrite=False)
    with ZipFile(candidate) as archive:
        original_text = {}
        for name in archive.namelist():
            if name.endswith((".xhtml", ".html")):
                body = ET.fromstring(archive.read(name)).find("{*}body")
                if body is not None:
                    original_text[name] = list(body.itertext())
    report = normalize_new_epub(candidate)
    write_json(run_dir / "normalization.json", {"reports": [report.to_dict()]})
    changes = []
    with ZipFile(candidate) as archive:
        for member, before in original_text.items():
            body = ET.fromstring(archive.read(member)).find("{*}body")
            after = list(body.itertext()) if body is not None else []
            for tag, i, j, k, l in difflib.SequenceMatcher(
                None, before, after, autojunk=False
            ).get_opcodes():
                if tag != "equal":
                    changes.append(
                        {"member": member, "before": before[i:j], "after": after[k:l]}
                    )
    write_json(run_dir / "normalization_diff.json", changes)
    if any(i.requires_codex_review or i.requires_user_review for i in report.issues):
        raise ValueError(
            "Normalization has unresolved findings; inspect normalization.json before importing"
        )
    second = normalize_epub(candidate, apply=False)
    if second.total_changes:
        raise ValueError(
            "Normalization is not stable; inspect the candidate before importing"
        )
    edition = read_epub_source(candidate)
    book = copy.deepcopy(edition.source)
    # Identity is derived from the original, not a regenerated modified timestamp.
    book["identifier"] = "local-edition:" + signature["sha256"]
    book["metadata_report"] = (
        report.metadata_enrichment.to_dict() if report.metadata_enrichment else {}
    )
    metadata_report = book["metadata_report"]
    if metadata_report.get("status") == "error":
        raise ValueError("Metadata lookup failed; inspect normalization.json and retry")
    if use_jjwxc_outline:
        if metadata_report.get("table_of_contents_error"):
            raise ValueError(
                "Official directory unavailable: "
                + metadata_report["table_of_contents_error"]
            )
        contents = metadata_report.get("table_of_contents")
        if contents:
            try:
                book["outline_report"] = apply_jjwxc_outline(
                    book, contents, aliases=chapter_aliases
                )
            except EditionOutlineError as error:
                write_json(
                    run_dir / "outline_review.json", {"differences": error.differences}
                )
                proposed = {d["local_title"]: d["official"] for d in error.differences}
                write_json(run_dir / "chapter_aliases.proposed.json", proposed)
                raise ValueError(
                    f"{error}; inspect {run_dir / 'outline_review.json'}, then supply --chapter-aliases with reviewed pairs"
                ) from error
    prepare_extra_sections(book)
    clean = run_dir / "prepared.epub"
    export_local(
        book,
        clean,
        cover=edition.cover,
        cover_mime=edition.cover_mime or "image/jpeg",
        prevent_overwrite=False,
    )
    final = normalize_epub(clean, apply=False)
    if final.total_changes:
        maintenance = normalize_and_review_epub(clean)
        write_json(run_dir / "prepared_normalization.json", maintenance.to_dict())
        if any(
            i.requires_codex_review or i.requires_user_review
            for i in maintenance.issues
        ):
            raise ValueError("Prepared archive has unresolved findings")
        refreshed = read_epub_source(clean).source
        for key in ("sections", "chapters", "extras"):
            book[key] = refreshed[key]
        final = normalize_epub(clean, apply=False)
    write_json(run_dir / "second_pass.json", final.to_dict())
    if final.total_changes:
        raise ValueError(
            "Prepared output requires additional normalization; inspect second_pass.json"
        )
    if digest(path.read_bytes()) != signature["sha256"]:
        raise ValueError("Original edition changed during preparation")
    if edition.cover:
        suffix = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(edition.cover_mime, "img")
        cover_name = "cover." + suffix
        (run_dir / cover_name).write_bytes(edition.cover)
        book["assets"] = {
            "cover": {
                "path": cover_name,
                "sha256": digest(edition.cover),
                "mime": edition.cover_mime,
            }
        }
    write_json(source_path, book)
    return book, edition.cover, edition.cover_mime


def ingest_local(
    path: Path,
    options: OutputOptions,
    *,
    run_dir: Path | None = None,
    title: str = "",
    author: str = "",
    chapter_aliases: dict[str, str] | None = None,
    use_jjwxc_outline: bool = True,
    cover_url: str | None = None,
) -> IngestResult:
    from src.notion.upload import upload_source
    from src.runtime.paths import resolve_output_path

    formats = requested_formats(options)
    directory = (
        run_dir or Path("generated/local_imports") / digest(path.read_bytes())[:16]
    )
    if path.suffix.lower() == ".json":
        book, cover, mime = load_prepared_source(path)
    else:
        book, cover, mime = prepare_local(
            path,
            directory,
            title=title,
            author=author,
            chapter_aliases=chapter_aliases,
            use_jjwxc_outline=use_jjwxc_outline,
        )
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
    for output in (epub_path, txt_path):
        if output and output.resolve() == path.resolve():
            raise ValueError(
                "Local ingest preserves the input; choose a different output path"
            )
        if output and options.prevent_overwrite and output.exists():
            raise ValueError(f"Output exists: {output}")
    if epub_path:
        export_local(
            book,
            epub_path,
            cover=cover,
            cover_mime=mime or "image/jpeg",
            prevent_overwrite=options.prevent_overwrite,
        )
    if txt_path:
        write_prepared_txt(book, txt_path)
    state = (
        upload_source(
            book, cover_bytes=cover if not cover_url else None, cover_url=cover_url
        )
        if "notion" in formats
        else None
    )
    return IngestResult(epub_path, txt_path, state)
