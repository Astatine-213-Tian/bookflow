"""Join crawl snapshots and translations before handing layout to the EPUB writer."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.content.html import render_paragraphs
from src.content.models import Chapter
from src.crawler.snapshot import load_chapter, load_manifest, snapshot_chapter_ids
from src.epub.bilingual import create_bilingual_book
from src.epub.maintenance import normalize_new_epub
from src.runtime.paths import resolve_output_path


def _translation_paragraph(text: str) -> str:
    return (
        '<p class="zh-translation" xml:lang="zh-CN">'
        + html.escape(text, quote=False)
        + "</p>"
    )


def _chapter_blocks(chapter: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = chapter.get("blocks")
    if isinstance(blocks, list) and blocks:
        return blocks
    output = []
    for item in chapter.get("paragraphs") or []:
        text = str(item.get("english") or "")
        output.append(
            {
                "type": "content",
                "index": int(item["index"]),
                "english": text,
                "html": f"<p>{html.escape(text, quote=False)}</p>",
            }
        )
    return output


def _load_translations(translations_dir: Path, chapter_id: str) -> dict[int, str]:
    path = translations_dir / f"{chapter_id}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        int(item["index"]): str(item.get("zh") or "").strip()
        for item in data.get("translations", [])
        if str(item.get("zh") or "").strip()
    }


def translated_chapter_blocks(chapter: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Keep both paragraph streams intact, interleaved at reviewed alignment boundaries."""
    groups = data.get("groups")
    if groups is None:
        groups = [{"english_indices": [x["index"]], "paragraphs": [x["zh"]]}
                  for x in data.get("translations", []) if x.get("zh")]
    else:
        expected = [x["index"] for x in chapter["paragraphs"]]
        if [i for g in groups for i in g["english_indices"]] != expected:
            raise ValueError("Grouped translation does not cover English exactly once")
        if any(not g["english_indices"] or not g["paragraphs"] or
               not all(p.strip() for p in g["paragraphs"]) for g in groups):
            raise ValueError("Empty alignment group")
    endings = {g["english_indices"][-1]: g["paragraphs"] for g in groups}
    parts: list[str] = []
    inside_group = False
    for block in _chapter_blocks(chapter):
        if block["type"] != "content" and inside_group and data.get("groups"):
            raise ValueError("Alignment crosses a source scene separator")
        if block.get("html"):
            parts.append(str(block["html"]))
        if block["type"] == "content":
            index = int(block["index"])
            inside_group = index not in endings
            parts.extend(_translation_paragraph(p) for p in endings.get(index, []))
    return parts


def build_bilingual_epub(
    *,
    snapshot_dir: Path,
    translations_dir: Path,
    output: Path | None,
    title: str | None = None,
    author: str | None = None,
) -> Path:
    manifest = load_manifest(snapshot_dir)
    book_title = title or str(manifest.get("title") or "book")
    book_author = author or str(manifest.get("author") or "")
    out_path = resolve_output_path(output, book_title, book_author)
    chapters = []
    for order, chapter_id in enumerate(snapshot_chapter_ids(manifest), 1):
        chapter = load_chapter(snapshot_dir, manifest, chapter_id)
        translation_path = translations_dir / f"{chapter_id}.json"
        data = json.loads(translation_path.read_text()) if translation_path.exists() else {}
        parts = translated_chapter_blocks(chapter, data)
        chapters.append(
            Chapter(
                str(chapter.get("title") or f"Chapter {order:03d}"), html_blocks=parts
            )
        )
    cover = manifest.get("cover") or {}
    cover_path = snapshot_dir / str(cover["path"]) if cover.get("path") else None
    create_bilingual_book(
        identifier=f"bilingual-{manifest.get('source', {}).get('provider', 'crawl')}-{book_title}",
        title=book_title,
        author=book_author,
        output=out_path,
        intro_html=render_paragraphs(manifest.get("intro_paragraphs") or []),
        chapters=chapters,
        volume_title=str(manifest.get("volume_title") or ""),
        cover=cover_path.read_bytes() if cover_path and cover_path.exists() else None,
        cover_mime=str(cover.get("mime") or "image/jpeg"),
    )
    normalize_new_epub(out_path)
    return out_path
