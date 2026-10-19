"""Stops where a translation run needs an agent decision before it can continue."""

from __future__ import annotations

from pathlib import Path


class ReviewRequired(ValueError):
    """A run paused for review; write the decisions under ``path`` and resume."""

    def __init__(self, kind: str, path: Path, message: str, items: list | None = None):
        super().__init__(message)
        self.kind = kind
        self.path = path
        self.items = items or []

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "message": str(self),
            "items": self.items,
        }
