"""Small HTML helpers for providers preserving source markup."""

from __future__ import annotations

import html
import re


def escape_text(text: str) -> str:
    return html.escape(text, quote=False)


def is_scene_break_text(text: str) -> bool:
    return bool(re.fullmatch(r"(?:\*\s*){3,}", text.strip()))


def render_scene_break() -> str:
    return '<p class="scene-break">***</p>'
