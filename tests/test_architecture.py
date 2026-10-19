"""Enforce the dependency boundaries that keep collection and output independent."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def imports(path: Path) -> set[str]:
    result = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            result.add(node.module)
        elif isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
    return result


class ArchitectureTests(unittest.TestCase):
    def test_production_modules_do_not_depend_on_cli_or_research(self):
        for path in SRC.rglob("*.py"):
            if path.parent == SRC / "cli":
                continue
            with self.subTest(module=path.relative_to(ROOT)):
                self.assertFalse(
                    {m for m in imports(path) if m.startswith(("src.cli", "research"))}
                )

    def test_collection_content_and_notion_have_no_epub_output_dependency(self):
        forbidden = {
            "crawler": (
                "src.epub",
                "src.notion",
                "src.dataset",
                "src.translation",
                "src.workflows",
            ),
            "content": ("src.epub", "src.notion", "src.crawler", "src.workflows"),
            "notion": ("src.epub", "src.crawler", "src.workflows", "src.translation"),
            "inputs": ("src.notion", "src.workflows", "src.translation", "src.cli"),
            "translation": ("src.crawler", "src.workflows", "src.notion", "src.cli"),
            "metadata": (
                "src.epub",
                "src.crawler",
                "src.notion",
                "src.content",
                "src.workflows",
            ),
        }
        for folder, prefixes in forbidden.items():
            for path in (SRC / folder).rglob("*.py"):
                with self.subTest(module=path.relative_to(ROOT)):
                    self.assertFalse(
                        {m for m in imports(path) if m.startswith(prefixes)}
                    )

    def test_presentation_never_runs_source_cleanup_or_remote_services(self):
        forbidden = (
            "src.content.normalization",
            "src.content.normalize",
            "src.content.html",
            "src.epub.maintenance",
            "src.epub.normalize",
            "src.epub.review",
            "src.metadata",
            "src.notion",
            "src.crawler",
            "src.translation",
        )
        for name in ("writer", "xhtml"):
            with self.subTest(renderer=name):
                self.assertFalse(
                    {
                        m
                        for m in imports(SRC / "epub" / f"{name}.py")
                        if m.startswith(forbidden)
                    }
                )


class CommandResultTests(unittest.TestCase):
    def test_commands_print_only_through_the_shared_result_line(self):
        for path in (SRC / "cli").glob("*.py"):
            if path.name == "output.py":
                continue
            with self.subTest(module=path.name):
                calls = [
                    node
                    for node in ast.walk(ast.parse(path.read_text()))
                    if isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "print"
                ]
                self.assertEqual(calls, [])

    def test_failures_end_with_a_json_result_line(self):
        import contextlib
        import io
        import json
        import tempfile

        from src.cli import (
            bilingual,
            compare_editions,
            crawl,
            prepare_book,
            update_book,
            validate_epub_chapters,
        )

        with tempfile.TemporaryDirectory() as root:
            missing = str(Path(root) / "missing")
            commands = {
                "book-crawl": (crawl.main, ["--output", missing]),
                "book-prepare": (prepare_book.main, [missing]),
                "book-update": (
                    update_book.main,
                    [missing, "--change", missing, "--run-dir", missing],
                ),
                "book-compare": (compare_editions.main, [missing, missing]),
                "book-validate-epub": (validate_epub_chapters.main, [root]),
                "book-bilingual": (bilingual.main, ["update", missing]),
            }
            for name, (main, argv) in commands.items():
                with self.subTest(command=name):
                    stdout = io.StringIO()
                    with (
                        contextlib.redirect_stdout(stdout),
                        contextlib.redirect_stderr(io.StringIO()),
                    ):
                        code = main(argv)
                    result = json.loads(stdout.getvalue().splitlines()[-1])
                    self.assertEqual((code, result["status"]), (1, "failed"))
                    self.assertTrue(result["error"])
