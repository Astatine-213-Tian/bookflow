"""The cover stage every book output passes through before it is written."""

from __future__ import annotations

from pathlib import Path

from src.content.cover import fit_restored_cover, normalize_cover
from src.runtime.files import write_json
from src.translation.gates import ReviewRequired

PROCEDURE = ".agents/skills/book-management/references/cover-normalization.md"
SUFFIX = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def deliver_cover(
    cover: bytes | None,
    mime: str,
    run_dir: Path,
    *,
    source: Path,
    replacement: Path | None = None,
    keep_original: bool = False,
) -> tuple[bytes | None, str, dict | None]:
    """Keep or slightly crop a 2:3 cover; pause for restoration otherwise.

    ``replacement`` is a user-approved restored cover. ``keep_original`` leaves an
    art book's or approved exception's cover untouched.
    """
    if replacement is not None:
        data, mime = fit_restored_cover(replacement.read_bytes())
        return data, mime, {"verdict": "replaced", "path": str(replacement)}
    if cover is None or keep_original:
        return cover, mime, None
    data, normalized_mime, assessment = normalize_cover(cover)
    if assessment.verdict != "restore":
        return data, normalized_mime, assessment.to_dict()
    run_dir.mkdir(parents=True, exist_ok=True)
    original = run_dir / f"cover-original.{SUFFIX.get(mime, 'img')}"
    original.write_bytes(cover)
    task = run_dir / "cover-restoration.json"
    write_json(
        task,
        {
            "original": str(original),
            "source": str(source),
            "assessment": assessment.to_dict(),
            "procedure": PROCEDURE,
        },
    )
    raise ReviewRequired(
        "cover",
        task,
        f"Cover needs restoration ({'; '.join(assessment.reasons)}). Follow "
        f"{PROCEDURE} with {original}. After the user approves, repeat the original "
        f"command with every option plus --cover APPROVED, reading the book from "
        f"{source} (a crawl then is not repeated); use --keep-original-cover instead "
        "for an art book or approved exception.",
        items=assessment.reasons,
    )
