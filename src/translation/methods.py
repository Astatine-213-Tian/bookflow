"""Translation methods behind one interface; a book spec selects one by name."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.runtime.paths import repo_root
from src.runtime.progress import ProgressLogger
from src.translation.config import config_path
from src.translation.glossary import load_glossary


@dataclass(frozen=True)
class Baseline:
    """A previously built snapshot and run whose unchanged chapters can be reused."""

    snapshot_dir: Path
    run_dir: Path


@dataclass(frozen=True)
class TranslateOptions:
    models: tuple[str, ...] | None = None
    codex_bin: str = "codex"
    timeout_seconds: int | None = None
    overwrite: bool = False
    run_codex: bool = True
    allow_missing: bool = False
    progress: ProgressLogger = field(default_factory=ProgressLogger)


@dataclass(frozen=True)
class TranslationMethod:
    """``translate`` produces outputs, ``validate`` runs review gates, ``ready``
    re-checks a finished run without model calls before anything is written."""

    name: str
    description: str
    translate: Callable[..., dict[str, Any]]
    validate: Callable[..., dict[str, Any]]
    ready: Callable[..., dict[str, Any]]
    output_dir: Callable[[Path], Path]
    reuses_baseline: bool = False


# ------------------------------------------------------------------------------
# Neutral prompts (optionally followed by author style transfer)
# ------------------------------------------------------------------------------


def _codex_timeout(config: dict[str, Any], override: int | None) -> int | None:
    if override is not None:
        return override
    value = (config.get("codex") or {}).get("timeout_seconds")
    return int(value) if value is not None else None


def _neutral_translate(
    *,
    snapshot_dir: Path,
    run_dir: Path,
    config: dict[str, Any],
    baseline: Baseline | None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.codex_cli import run_missing_prompts_with_model_fallback
    from src.translation.prompt_builder import prepare_prompts
    from src.translation.style_transfer import configured_model_order

    run_dir.mkdir(parents=True, exist_ok=True)
    prepare_prompts(
        snapshot_dir=snapshot_dir.expanduser().resolve(),
        run_dir=run_dir,
        config=config,
        glossary=load_glossary(config_path(config, "glossary_path")),
    )
    options.progress.info(f"prepared neutral translation run {run_dir}")
    if not options.run_codex:
        return {"run_dir": str(run_dir), "codex": "skipped"}
    summary = run_missing_prompts_with_model_fallback(
        run_dir=run_dir,
        models=configured_model_order(config, options.models),
        codex_bin=options.codex_bin,
        chunk_ids=None,
        overwrite=options.overwrite,
        timeout_seconds=_codex_timeout(config, options.timeout_seconds),
    )
    options.progress.info(
        "completed neutral translation "
        f"(chunks {summary['completed']}, skipped {summary['skipped']}, "
        f"recovered {summary['recovered']}, still missing {summary['still_missing']}, "
        f"model {summary.get('effective_model') or 'default'})"
    )
    return summary


def protect_sentence_translations(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    from src.translation.sentence_translations import (
        apply_sentence_translation_overrides,
    )

    run_dir = run_dir.expanduser().resolve()
    if snapshot_dir is None:
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        raw = manifest.get("snapshot_dir")
        if not raw:
            raise ValueError(
                f"translation run has no snapshot_dir: {run_dir / 'run_manifest.json'}"
            )
        snapshot_dir = Path(str(raw)).expanduser()
        if not snapshot_dir.is_absolute():
            snapshot_dir = repo_root() / snapshot_dir
    return apply_sentence_translation_overrides(
        run_dir=run_dir,
        snapshot_dir=snapshot_dir,
        glossary=load_glossary(config_path(config, "glossary_path")),
    )


def _neutral_validate(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.validation import validate_and_merge

    run_dir = run_dir.expanduser().resolve()
    summary = validate_and_merge(run_dir, allow_missing=options.allow_missing)
    protected = protect_sentence_translations(
        run_dir=run_dir, config=config, snapshot_dir=snapshot_dir
    )
    summary["sentence_translations"] = {
        "entry_count": protected["entry_count"],
        "occurrence_count": protected["occurrence_count"],
        "changed_occurrence_count": protected["changed_occurrence_count"],
        "unresolved_count": len(protected["unresolved"]),
    }
    options.progress.info(
        f"validated {len(summary['chunks'])} chunk(s); "
        f"{summary.get('glossary_candidate_count') or 0} glossary candidate(s) in "
        f"{run_dir / 'glossary_candidates.json'} for review"
    )
    return summary


def _style_dir(run_dir: Path) -> Path:
    return run_dir.expanduser().resolve() / "author_style_transfer"


def _style_translate(
    *,
    snapshot_dir: Path,
    run_dir: Path,
    config: dict[str, Any],
    baseline: Baseline | None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.style_transfer import (
        prepare_style_transfer_run,
        run_style_transfer,
    )

    neutral = _neutral_translate(
        snapshot_dir=snapshot_dir,
        run_dir=run_dir,
        config=config,
        baseline=None,
        options=options,
    )
    _neutral_validate(
        run_dir=run_dir,
        config=config,
        snapshot_dir=snapshot_dir,
        options=TranslateOptions(progress=options.progress),
    )
    style_dir = _style_dir(run_dir)
    prepare_style_transfer_run(
        semantic_run_dir=run_dir.expanduser().resolve(),
        style_run_dir=style_dir,
        config=config,
    )
    options.progress.info(f"prepared author style-transfer run {style_dir}")
    if not options.run_codex:
        return {"neutral": neutral, "style": "skipped"}
    summary = run_style_transfer(
        style_run_dir=style_dir,
        config=config,
        models=options.models,
        codex_bin=options.codex_bin,
        timeout_seconds=options.timeout_seconds,
        overwrite=options.overwrite,
    )
    options.progress.info(
        "completed author style transfer "
        f"(completed {summary['completed_count']}, "
        f"skipped {summary['skipped_count']}, failures {summary['failure_count']})"
    )
    if int(summary["failure_count"]) > 0:
        raise RuntimeError(
            f"author style transfer has {summary['failure_count']} failed chunk(s)"
        )
    return {"neutral": neutral, "style": summary}


def run_semantic_qa(
    *,
    run_dir: Path,
    config: dict[str, Any],
    options: TranslateOptions,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Review styled output for semantic loss; any unresolved finding is fatal."""
    from src.translation.semantic_compression import (
        DEFAULT_BATCH_SIZE,
        DEFAULT_MAX_CANDIDATES,
        DEFAULT_MIN_CONFIDENCE,
        run_semantic_compression_qa,
    )
    from src.translation.style_transfer import configured_model_order

    semantic = config.get("semantic_compression") or {}
    timeout = (
        options.timeout_seconds
        if options.timeout_seconds is not None
        else semantic.get(
            "timeout_seconds", (config.get("codex") or {}).get("timeout_seconds")
        )
    )
    summary = run_semantic_compression_qa(
        run_dir=run_dir,
        config=config,
        output_dir=None,
        max_candidates=int(semantic.get("max_candidates") or DEFAULT_MAX_CANDIDATES),
        batch_size=int(semantic.get("batch_size") or DEFAULT_BATCH_SIZE),
        models=configured_model_order(config, options.models),
        codex_bin=options.codex_bin,
        timeout_seconds=int(timeout) if timeout is not None else None,
        auto_repair=bool(semantic.get("auto_repair")),
        min_auto_apply_confidence=str(
            semantic.get("min_auto_apply_confidence") or DEFAULT_MIN_CONFIDENCE
        ),
        dry_run=False,
        overwrite=overwrite,
    )
    result = summary["result_summary"]
    options.progress.info(
        "semantic QA complete "
        f"(candidates {summary['candidate_summary']['candidate_count']}, "
        f"applied {result['applied_count']}, rejected {result['rejected_count']}, "
        f"unresolved losses {result.get('unresolved_true_loss_count', 0)}, "
        f"failures {result['failure_count']})"
    )
    for key, label in (
        ("failure_count", "failed review batch(es)"),
        ("rejected_count", "rejected candidate(s)"),
        ("unresolved_true_loss_count", "unresolved true-loss candidate(s)"),
    ):
        if int(result.get(key) or 0) > 0:
            raise RuntimeError(f"semantic QA has {result[key]} {label}")
    return summary


def _semantic_summary_path(style_dir: Path) -> Path:
    return style_dir / "semantic_compression" / "semantic_compression_summary.json"


def _require_auto_review(config: dict[str, Any]) -> None:
    if not bool((config.get("semantic_compression") or {}).get("auto_review")):
        raise ValueError(
            "neutral_style_transfer requires semantic_compression.auto_review"
        )


def _style_validate(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.semantic_compression import semantic_qa_summary_is_current
    from src.translation.style_transfer import validate_style_transfer_provenance

    style_dir = _style_dir(run_dir)
    _require_auto_review(config)
    provenance = validate_style_transfer_provenance(style_dir)
    options.progress.info(
        f"verified {provenance['validated_chunk_count']} style artifact binding(s)"
    )
    summary = _neutral_validate(
        run_dir=style_dir, config=config, snapshot_dir=snapshot_dir, options=options
    )
    qa_path = _semantic_summary_path(style_dir)
    current = semantic_qa_summary_is_current(style_dir, qa_path, config)
    if current and not options.overwrite:
        options.progress.info(f"reusing current semantic QA summary {qa_path}")
        return summary
    if qa_path.exists() and not current:
        options.progress.info("styled outputs changed; rerunning semantic QA")
    qa = run_semantic_qa(
        run_dir=style_dir,
        config=config,
        options=options,
        overwrite=options.overwrite or not current,
    )
    if int(qa["result_summary"]["applied_count"]) > 0:
        summary = _neutral_validate(
            run_dir=style_dir,
            config=config,
            snapshot_dir=snapshot_dir,
            options=options,
        )
    return summary


def _neutral_ready(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.validation import validate_and_merge

    summary = validate_and_merge(
        run_dir.expanduser().resolve(), allow_missing=options.allow_missing
    )
    protect_sentence_translations(
        run_dir=run_dir, config=config, snapshot_dir=snapshot_dir
    )
    return summary


def _style_ready(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.semantic_compression import semantic_qa_summary_is_current
    from src.translation.style_transfer import validate_style_transfer_provenance

    style_dir = _style_dir(run_dir)
    _require_auto_review(config)
    validate_style_transfer_provenance(style_dir)
    summary = _neutral_ready(
        run_dir=style_dir, config=config, snapshot_dir=snapshot_dir, options=options
    )
    if not semantic_qa_summary_is_current(
        style_dir, _semantic_summary_path(style_dir), config
    ):
        raise ValueError(
            "styled output has no current semantic QA summary; run "
            "`book-bilingual validate` before building"
        )
    return summary


# ------------------------------------------------------------------------------
# Direct positive scenes
# ------------------------------------------------------------------------------


def _positive_translate(
    *,
    snapshot_dir: Path,
    run_dir: Path,
    config: dict[str, Any],
    baseline: Baseline | None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.positive_scene import run_positive_scenes

    summary = run_positive_scenes(
        snapshot_dir=snapshot_dir,
        run_dir=run_dir,
        config=config,
        baseline_snapshot=baseline.snapshot_dir if baseline else None,
        baseline_run=baseline.run_dir if baseline else None,
    )
    options.progress.info(
        f"validated {len(summary['chunks'])} positive scene(s); "
        f"reused {summary['reused_chapters']} chapter(s)"
    )
    return summary


def _positive_validate(
    *,
    run_dir: Path,
    config: dict[str, Any],
    snapshot_dir: Path | None = None,
    options: TranslateOptions,
) -> dict[str, Any]:
    from src.translation.positive_scene import validate_positive_run

    return validate_positive_run(
        run_dir.expanduser().resolve(), config=config, snapshot_dir=snapshot_dir
    )


# ------------------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------------------


METHODS: dict[str, TranslationMethod] = {
    method.name: method
    for method in (
        TranslationMethod(
            "direct_scene_positive",
            "Positive-example scenes, source QA and non-rewriting alignment",
            _positive_translate,
            _positive_validate,
            _positive_validate,
            lambda run_dir: run_dir.expanduser().resolve(),
            reuses_baseline=True,
        ),
        TranslationMethod(
            "neutral",
            "Neutral Chinese prompts with protected sentence translations",
            _neutral_translate,
            _neutral_validate,
            _neutral_ready,
            lambda run_dir: run_dir.expanduser().resolve(),
        ),
        TranslationMethod(
            "neutral_style_transfer",
            "Neutral prompts, author style transfer and semantic QA",
            _style_translate,
            _style_validate,
            _style_ready,
            _style_dir,
        ),
    )
}


def method_for(config: dict[str, Any]) -> TranslationMethod:
    name = (config.get("translation") or {}).get("method")
    if name not in METHODS:
        raise ValueError(
            f"Book spec translation.method must be one of {sorted(METHODS)}; "
            f"got {name!r}"
        )
    return METHODS[name]
