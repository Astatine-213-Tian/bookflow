"""Bilingual books: collect the spec's source, translate it, write the outputs.

Each stage runs on its own; ``update`` chains them for one book spec, resumes a
paused run and records the last successful build as the next reuse baseline.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.crawler.models import CrawlOptions
from src.runtime.files import write_json
from src.runtime.paths import work_root
from src.runtime.progress import ProgressLogger
from src.translation.config import book_slug, load_config
from src.translation.methods import (
    Baseline,
    TranslateOptions,
    TranslationMethod,
    method_for,
)
from src.workflows.collect import collect_source, crawl_options
from src.workflows.ingest import IngestResult, OutputOptions, write_book

RUN_RECORD = "bilingual_run.json"
COMMENT_EVIDENCE = "glossary_comment_evidence.json"


def _relative(path: Path) -> str:
    path = path.expanduser().resolve()
    try:
        return str(path.relative_to(work_root()))
    except ValueError:
        return str(path)


def _absolute(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else work_root() / path


# ------------------------------------------------------------------------------
# Stage 1: collect
# ------------------------------------------------------------------------------


def collect_snapshot(
    config: dict[str, Any],
    output: Path,
    *,
    options: CrawlOptions | None = None,
) -> Path:
    source = config.get("source") or {}
    if not source.get("url"):
        raise ValueError("Book spec has no source.url to collect")
    return collect_source(
        source["url"],
        output,
        provider=source.get("provider"),
        options=options or crawl_options(config),
    )


def write_comment_evidence(
    snapshot_dir: Path, config: dict[str, Any], output: Path | None = None
) -> dict[str, Any]:
    from src.translation.comments import write_glossary_comment_evidence

    output = output or snapshot_dir / COMMENT_EVIDENCE
    evidence = write_glossary_comment_evidence(
        snapshot_dir=snapshot_dir,
        output_path=output,
        authors=tuple(config.get("comment_authorities", [])),
    )
    return {**evidence, "path": str(output.expanduser().resolve())}


# ------------------------------------------------------------------------------
# Stage 2: translate and validate with the spec's method
# ------------------------------------------------------------------------------


def _bind_run(
    run_dir: Path,
    method: TranslationMethod,
    snapshot_dir: Path,
    baseline: Baseline | None,
) -> None:
    record = {
        "method": method.name,
        "snapshot_dir": _relative(snapshot_dir),
        "baseline": (
            {
                "snapshot_dir": _relative(baseline.snapshot_dir),
                "run_dir": _relative(baseline.run_dir),
            }
            if baseline
            else None
        ),
    }
    path = run_dir / RUN_RECORD
    if path.exists() and json.loads(path.read_text()) != record:
        raise ValueError(
            f"{run_dir} belongs to another method, snapshot or baseline; "
            "use a fresh run directory"
        )
    write_json(path, record)


def _method_for_run(run_dir: Path, config: dict[str, Any]) -> TranslationMethod:
    method = method_for(config)
    path = run_dir.expanduser() / RUN_RECORD
    if path.exists():
        recorded = json.loads(path.read_text())["method"]
        if recorded != method.name:
            raise ValueError(
                f"{run_dir} was translated with {recorded}; the spec selects "
                f"{method.name}"
            )
    return method


def translate_snapshot(
    snapshot_dir: Path,
    run_dir: Path,
    config: dict[str, Any],
    *,
    baseline: Baseline | None = None,
    options: TranslateOptions | None = None,
) -> dict[str, Any]:
    options = options or TranslateOptions()
    method = method_for(config)
    baseline = baseline if method.reuses_baseline else None
    run_dir.mkdir(parents=True, exist_ok=True)
    _bind_run(run_dir, method, snapshot_dir, baseline)
    return method.translate(
        snapshot_dir=snapshot_dir,
        run_dir=run_dir,
        config=config,
        baseline=baseline,
        options=options,
    )


def validate_run(
    run_dir: Path,
    config: dict[str, Any],
    *,
    snapshot_dir: Path | None = None,
    options: TranslateOptions | None = None,
) -> dict[str, Any]:
    return _method_for_run(run_dir, config).validate(
        run_dir=run_dir,
        config=config,
        snapshot_dir=snapshot_dir,
        options=options or TranslateOptions(),
    )


# ------------------------------------------------------------------------------
# Stage 3: write the bilingual book
# ------------------------------------------------------------------------------


def output_options(config: dict[str, Any], output: Path | None = None) -> OutputOptions:
    """An explicit ``output`` writes that EPUB; otherwise the spec's ``output``."""
    if output is not None:
        return OutputOptions(
            output=output, output_formats=("epub",), prevent_overwrite=False
        )
    targets = config.get("output") or {"epub": None}
    unknown = set(targets) - {"epub", "txt"}
    if unknown:
        raise ValueError(f"Unsupported bilingual outputs: {sorted(unknown)}")
    return OutputOptions(
        output=_absolute(targets["epub"]) if targets.get("epub") else None,
        txt_output=_absolute(targets["txt"]) if targets.get("txt") else None,
        output_formats=tuple(targets),
        prevent_overwrite=False,
    )


def build_book(
    snapshot_dir: Path,
    run_dir: Path,
    config: dict[str, Any],
    *,
    output: Path | None = None,
    options: TranslateOptions | None = None,
) -> IngestResult:
    options = options or TranslateOptions()
    method = _method_for_run(run_dir, config)
    method.ready(
        run_dir=run_dir, config=config, snapshot_dir=snapshot_dir, options=options
    )
    return write_bilingual(
        snapshot_dir,
        method.output_dir(run_dir) / "translations",
        output_options(config, output),
        title=str(config.get("title") or "") or None,
        author=str(config.get("author") or "") or None,
    )


def write_bilingual(
    snapshot_dir: Path,
    translations_dir: Path,
    outputs: OutputOptions,
    *,
    title: str | None = None,
    author: str | None = None,
) -> IngestResult:
    """Join translations to the snapshot, prepare once, then write the outputs."""
    from src.translation.output import translated_source
    from src.workflows.prepare import prepare_book, save_prepared

    book, cover, mime = translated_source(
        snapshot_dir, translations_dir, title=title, author=author
    )
    book, reports = prepare_book(book)
    save_prepared(book, translations_dir.parent / "prepared", reports, cover, mime)
    return write_book(book, outputs, cover=cover, cover_mime=mime)


# ------------------------------------------------------------------------------
# update: chain the stages for one book spec
# ------------------------------------------------------------------------------


def book_root(slug: str) -> Path:
    """``bilingual/<book>/`` holds the book's snapshots, runs and state."""
    return work_root() / "bilingual" / slug


def state_path(slug: str) -> Path:
    return book_root(slug) / "state.json"


def load_state(slug: str) -> dict[str, Any]:
    path = state_path(slug)
    if not path.exists():
        return {"baseline": None, "pending": None}
    return json.loads(path.read_text())


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _start_pending(
    state: dict[str, Any], slug: str, *, restart: bool, recrawl: bool
) -> dict[str, Any]:
    stamp = _stamp()
    pending = state.get("pending")
    if recrawl or not pending:
        pending = {
            "snapshot": f"bilingual/{slug}/snapshots/{stamp}",
            "run": f"bilingual/{slug}/runs/{stamp}",
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
    elif restart:
        pending = {**pending, "run": f"bilingual/{slug}/runs/{stamp}"}
    state["pending"] = pending
    write_json(state_path(slug), state)
    return pending


def _ensure_snapshot(
    config: dict[str, Any], snapshot: Path, *, headless: bool, progress: ProgressLogger
) -> None:
    if (snapshot / "evidence.json").exists():
        progress.info(f"reusing collected snapshot {snapshot}")
        return
    if snapshot.exists() and any(snapshot.iterdir()):
        raise ValueError(
            f"Pending snapshot {snapshot} is incomplete; rerun with --recrawl"
        )
    progress.section("Collect")
    collect_snapshot(config, snapshot, options=crawl_options(config, headless=headless))


def _usable_baseline(
    state: dict[str, Any], method: TranslationMethod, progress: ProgressLogger
) -> Baseline | None:
    recorded = state.get("baseline")
    if not recorded or not method.reuses_baseline:
        return None
    if recorded.get("method") != method.name:
        progress.info(
            f"baseline used {recorded.get('method')}; translating without reuse"
        )
        return None
    baseline = Baseline(_absolute(recorded["snapshot"]), _absolute(recorded["run"]))
    if not (baseline.snapshot_dir / "source.json").exists() or not (
        baseline.run_dir.exists()
    ):
        progress.warning("baseline files are missing; translating without reuse")
        return None
    return baseline


def update_book(
    book: str | Path,
    *,
    restart: bool = False,
    recrawl: bool = False,
    headless: bool = False,
    output: Path | None = None,
    options: TranslateOptions | None = None,
) -> dict[str, Any]:
    """Collect, translate, validate and write one book, resuming a paused run.

    ``restart`` starts a fresh translation run on the pending snapshot;
    ``recrawl`` also collects a fresh snapshot.
    """
    options = options or TranslateOptions()
    progress = options.progress
    config = load_config(book)
    slug = book_slug(config)
    method = method_for(config)
    state = load_state(slug)
    pending = _start_pending(state, slug, restart=restart, recrawl=recrawl)
    snapshot, run = _absolute(pending["snapshot"]), _absolute(pending["run"])
    _ensure_snapshot(config, snapshot, headless=headless, progress=progress)
    comments = None
    if config.get("comment_authorities"):
        comments = write_comment_evidence(snapshot, config)
        progress.info(
            f"{comments['authoritative_reply_count']} authoritative comment "
            f"repl(ies) for glossary review in {comments['path']}"
        )

    baseline = _usable_baseline(state, method, progress)
    progress.section(f"Translate ({method.name})")
    translate_snapshot(snapshot, run, config, baseline=baseline, options=options)
    progress.section("Validate")
    validate_run(run, config, snapshot_dir=snapshot, options=options)
    progress.section("Build")
    written = build_book(snapshot, run, config, output=output, options=options)

    outputs = {
        name: _relative(path)
        for name, path in (("epub", written.epub_path), ("txt", written.txt_path))
        if path
    }
    state = {
        "baseline": {
            "snapshot": pending["snapshot"],
            "run": pending["run"],
            "method": method.name,
            "outputs": outputs,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        },
        "pending": None,
    }
    write_json(state_path(slug), state)
    check = written.epub_check
    return {
        "status": "complete",
        "book": slug,
        "method": method.name,
        "snapshot": pending["snapshot"],
        "run": pending["run"],
        "reused_baseline": (
            {
                "snapshot": _relative(baseline.snapshot_dir),
                "run": _relative(baseline.run_dir),
            }
            if baseline
            else None
        ),
        "outputs": outputs,
        "comment_evidence": comments["path"] if comments else None,
        "epub_check": list(check.issues) if check else None,
    }


# ------------------------------------------------------------------------------
# seed: recover a baseline from a bilingual EPUB this repository built
# ------------------------------------------------------------------------------


def _expected_english(snapshot: Path) -> dict[str, list[list[str]]]:
    """English paragraphs per chapter as raw source and as the build renders them.

    A bilingual build normalizes the joined book, so the EPUB's English may be the
    normalized form; both forms identify the same reviewed source text.
    """
    from tempfile import TemporaryDirectory

    from src.content.html import is_scene_break_text
    from src.translation.output import translated_source
    from src.translation.source import chapter_ids, load_chapter, load_source
    from src.workflows.prepare import prepare_book

    source = load_source(snapshot)
    with TemporaryDirectory() as empty:
        joined, _, _ = translated_source(snapshot, Path(empty))
    rendered, _ = prepare_book(joined)
    rendered_chapters = {
        **rendered["chapters"],
        **{extra["id"]: extra for extra in rendered["extras"]},
    }
    result = {}
    for cid in chapter_ids(source):
        raw = [p["english"] for p in load_chapter(source, cid)["paragraphs"]]
        normalized = []
        for block in rendered_chapters[cid]["blocks"]:
            text = "".join(r["text"] for r in block.get("runs", []))
            if block.get("kind") == "divider" or is_scene_break_text(text):
                continue
            if text.strip():
                normalized.append(text)
        result[cid] = [raw, normalized]
    return result


def seed_baseline(
    book: str | Path,
    epub: Path,
    *,
    replace: bool = False,
    headless: bool = False,
    progress: ProgressLogger | None = None,
) -> dict[str, Any]:
    """Make the pending snapshot's baseline from translations already in ``epub``.

    A chapter is seeded only when its English in the EPUB matches the snapshot
    exactly; the next ``update`` translates every other chapter.
    """
    from src.translation.seed import matching_groups, read_bilingual_epub

    progress = progress or ProgressLogger()
    config = load_config(book)
    slug = book_slug(config)
    method = method_for(config)
    if not method.reuses_baseline:
        raise ValueError(f"{method.name} does not reuse a baseline; nothing to seed")
    state = load_state(slug)
    if state.get("baseline") and not replace:
        raise ValueError(
            "This book already has a baseline; pass --replace to seed over it"
        )
    pending = _start_pending(state, slug, restart=False, recrawl=False)
    snapshot = _absolute(pending["snapshot"])
    _ensure_snapshot(config, snapshot, headless=headless, progress=progress)

    progress.section("Seed")
    recovered = read_bilingual_epub(epub)
    run = book_root(slug) / "runs" / f"seed-{_stamp()}"
    seeded, unmatched = [], {}
    for cid, forms in _expected_english(snapshot).items():
        if cid not in recovered:
            unmatched[cid] = "not in EPUB"
            continue
        groups = next(
            (g for form in forms if (g := matching_groups(form, recovered[cid]))),
            None,
        )
        if groups is None:
            unmatched[cid] = recovered[cid].get("error") or "English differs"
            continue
        write_json(
            run / "translations" / f"{cid}.json", {"chapter_id": cid, "groups": groups}
        )
        seeded.append(cid)
    write_json(
        run / RUN_RECORD,
        {
            "method": method.name,
            "snapshot_dir": pending["snapshot"],
            "seeded_from": _relative(epub),
        },
    )
    state["baseline"] = {
        "snapshot": pending["snapshot"],
        "run": _relative(run),
        "method": method.name,
        "seeded_from": _relative(epub),
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_json(state_path(slug), state)
    progress.info(
        f"seeded {len(seeded)} chapter(s) from {epub}; "
        f"{len(unmatched)} will be translated"
    )
    return {
        "status": "complete",
        "book": slug,
        "snapshot": pending["snapshot"],
        "baseline_run": _relative(run),
        "seeded": seeded,
        "to_translate": unmatched,
        "next": f"book bilingual update {slug}",
    }
