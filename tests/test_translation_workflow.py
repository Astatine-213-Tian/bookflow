"""Exercise real CLI stages over the shared content contract, without LLM calls."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from src.runtime.files import write_json
from tests.fixtures import write_source
from tests.test_production_style_transfer import (
    ASSET_PATH,
    ASSET_SHA256,
    PROMPT_PATH,
    SCHEMA_PATH,
)


class TranslationWorkflowTests(unittest.TestCase):
    def test_spec_selects_method_through_translate_validate_and_build_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, run = root / "input", root / "run"
            write_source(source, ["The door opened.", "Keep this promise."])
            glossary = root / "glossary.json"
            write_json(
                glossary,
                {
                    "terms": {},
                    "sentence_translations": [
                        {"source": ["Keep this promise."], "zh": ["守住这个承诺。"]}
                    ],
                },
            )
            config = root / "config.json"
            spec = {
                "glossary_path": str(glossary),
                "translation": {"method": "neutral"},
                "style_transfer": {
                    "asset_path": str(ASSET_PATH),
                    "asset_file_sha256": ASSET_SHA256,
                    "prompt_path": str(PROMPT_PATH),
                    "schema_path": str(SCHEMA_PATH),
                },
            }
            write_json(config, spec)

            def cli(*args: str) -> dict:
                result = subprocess.run(
                    ["uv", "run", "book", "bilingual", *map(str, args)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout.splitlines()[-1])

            cli("translate", source, "--book", config, "--run-dir", run, "--no-codex")
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual(manifest["chunks"][0]["indexes"], [0, 1])
            for chunk in manifest["chunks"]:
                write_json(
                    run / chunk["json_output_path"],
                    {
                        "translations": [
                            {"index": 0, "zh": "门开了。"},
                            {"index": 1, "zh": "另一种译法。"},
                        ]
                    },
                )
            validated = cli("validate", run, "--book", config)
            self.assertEqual(validated["status"], "complete")
            self.assertEqual(
                json.loads((run / "translations/01.json").read_text())["translations"][
                    1
                ]["zh"],
                "守住这个承诺。",
            )
            styled, styled_config = root / "styled", root / "styled.json"
            shutil.copytree(run, styled)
            (styled / "bilingual_run.json").unlink()
            write_json(
                styled_config,
                {**spec, "translation": {"method": "neutral_style_transfer"}},
            )
            cli(
                "translate",
                source,
                "--book",
                styled_config,
                "--run-dir",
                styled,
                "--no-codex",
            )
            request = json.loads(
                next(
                    (styled / "author_style_transfer/requests").glob("*.json")
                ).read_text()
            )
            self.assertEqual(
                [row["zh"] for row in request["neutral_zh"]],
                ["门开了。", "守住这个承诺。"],
            )
            output = root / "book.epub"
            built = cli(
                "build", source, "--run-dir", run, "--book", config, "-o", output
            )
            self.assertEqual(built["epub_check"], [])
            with ZipFile(output) as archive:
                body = archive.read("EPUB/chapter_0001.xhtml").decode()
                for text in (
                    "The door opened.",
                    "Keep this promise.",
                    "门开了。",
                    "守住这个承诺。",
                ):
                    self.assertIn(text, body)
                self.assertIn("Chapter 1", archive.read("EPUB/nav.xhtml").decode())
            self.assertTrue((run / "prepared/report.json").exists())
            self.assertEqual(
                json.loads((run / "prepared/source.json").read_text())["source_format"],
                "translation",
            )
