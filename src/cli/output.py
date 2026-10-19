"""Every command ends with one JSON result line on stdout; logs go to stderr.

``status`` is ``complete`` (exit 0), ``issues_found`` (exit 1: a check ran and
found problems), ``failed`` (exit 1) or ``review_required`` (exit 2: write the
decisions under ``review.path``, then run ``resume``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from src.translation.gates import ReviewRequired

EXIT_CODES = {"complete": 0, "issues_found": 1, "failed": 1, "review_required": 2}


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, default=str), flush=True)


def paths(**items: Path | None) -> dict[str, str]:
    """Output paths for a result, leaving out the ones not written."""
    return {name: str(path) for name, path in items.items() if path is not None}


def run_command(
    body: Callable[[], dict[str, Any]],
    *,
    describe: Callable[[BaseException], str] = str,
    resume: str | None = None,
    interrupted: str = "Interrupted; rerun to resume",
) -> int:
    """Run ``body`` and emit its result, or the failure, as the last stdout line."""
    try:
        result = body()
    except ReviewRequired as review:
        log(str(review))
        result = {"status": "review_required", "review": review.as_dict()}
        if resume:
            result["resume"] = resume
    except KeyboardInterrupt:
        log(interrupted)
        result = {"status": "failed", "error": interrupted}
    except Exception as error:  # noqa: BLE001 - the CLI boundary reports every failure
        message = describe(error)
        log(message)
        result = {"status": "failed", "error": message}
    result.setdefault("status", "complete")
    emit(result)
    return EXIT_CODES[result["status"]]
