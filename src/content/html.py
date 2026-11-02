"""Small HTML helpers for providers preserving source markup."""

from __future__ import annotations

import html
import re


def escape_text(text: str) -> str:
    return html.escape(text, quote=False)


def is_scene_break_text(text: str) -> bool:
    return bool(re.fullmatch(r"(?:\*\s*){3,}", text.strip()))


def alignment_style(alignment: str | None) -> str:
    """Inline alignment the shared HTML input reads back into a block."""
    return f' style="text-align: {alignment}"' if alignment else ""


def render_scene_break(alignment: str | None = None) -> str:
    return f'<p class="scene-break"{alignment_style(alignment)}>***</p>'
