"""Resume, reuse and gate behavior of ``book-bilingual update`` without model calls."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from src.cli.bilingual import main as bilingual_main
from src.runtime.files import write_json
from src.translation.gates import ReviewRequired
from src.translation.methods import METHODS, TranslationMethod
from tests.fixtures import write_source


class FakeMethod:
    """Records calls; translates every paragraph unless a review gate is armed."""

    def __init__(self):
        self.baselines = []
        self.gate = False

    def translate(self, *, snapshot_dir, run_dir, config, baseline, options):
        self.baselines.append(baseline)
        if self.gate:
            raise ReviewRequired("fake_review", run_dir / "decisions", "decide first")
        write_json(
            run_dir / "translations" / "01.json",
            {"translations": [{"index": 0, "zh": "门开了。"}]},
        )
        return {}

    def validate(self, *, run_dir, config, snapshot_dir=None, options):
        if not (run_dir / "translations" / "01.json").exists():
            raise ValueError("missing translations")
        return {"chunks": []}

    def method(self) -> TranslationMethod:
        return TranslationMethod(
            "fake",
            "test double",
            self.translate,
            self.validate,
            self.validate,
            lambda run_dir: run_dir,
            reuses_baseline=True,
        )


class BilingualUpdateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        spec = self.root / "book_specs" / "fake_book" / "config.json"
        write_json(
            spec,
            {
                "title": "门",
                "author": "作者",
                "glossary_path": "book_specs/fake_book/glossary.json",
                "translation": {"method": "fake"},
                "output": {"epub": "books/作者/门.bilingual.epub"},
                "source": {"provider": "fixture", "url": "https://example.org/book"},
            },
        )
        self.fake = FakeMethod()
        self.collections = []

        def collect(config, output, *, options=None):
            self.collections.append(output)
            write_source(output, ["The door opened."])
            write_json(output / "evidence.json", {})
            return output / "source.json"

        for target in (
            patch("src.workflows.bilingual.repo_root", return_value=self.root),
            patch("src.translation.config.repo_root", return_value=self.root),
            patch("src.workflows.bilingual.collect_snapshot", side_effect=collect),
            patch.dict(METHODS, {"fake": self.fake.method()}),
            patch("src.workflows.prepare.enrich_source", return_value={}),
        ):
            self.enterContext(target)

    def update(self, *args: str) -> tuple[int, dict]:
        with patch("builtins.print") as printed:
            code = bilingual_main(["update", "fake_book", *args])
        return code, json.loads(printed.call_args_list[-1].args[0])

    def state(self) -> dict:
        return json.loads((self.root / "bilingual/fake_book/state.json").read_text())

    def test_first_update_builds_and_records_the_next_baseline(self):
        code, result = self.update()
        self.assertEqual((code, result["status"]), (0, "complete"))
        self.assertIsNone(self.fake.baselines[0])
        epub = self.root / result["outputs"]["epub"]
        self.assertEqual(result["outputs"]["epub"], "books/作者/门.bilingual.epub")
        with ZipFile(epub) as archive:
            body = archive.read("EPUB/chapter_0001.xhtml").decode()
        self.assertIn("The door opened.", body)
        self.assertIn("门开了。", body)
        state = self.state()
        self.assertIsNone(state["pending"])
        self.assertEqual(state["baseline"]["run"], result["run"])
        self.assertEqual(state["baseline"]["method"], "fake")

        with patch("src.workflows.bilingual.datetime") as clock:
            clock.now.return_value.strftime.return_value = "later"
            clock.now.return_value.isoformat.return_value = "later"
            code, second = self.update()
        self.assertEqual(code, 0)
        reused = self.fake.baselines[1]
        self.assertEqual(reused.run_dir, self.root / result["run"])
        self.assertEqual(reused.snapshot_dir, self.root / result["snapshot"])
        self.assertNotEqual(second["run"], result["run"])

    def test_review_stop_resumes_the_same_snapshot_and_run(self):
        self.fake.gate = True
        code, stopped = self.update()
        self.assertEqual((code, stopped["status"]), (2, "review_required"))
        self.assertEqual(stopped["review"]["kind"], "fake_review")
        self.assertEqual(stopped["resume"], "book-bilingual update fake_book")
        pending = self.state()["pending"]

        self.fake.gate = False
        code, result = self.update()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.collections), 1)
        self.assertEqual(result["run"], pending["run"])
        self.assertEqual(result["snapshot"], pending["snapshot"])

    def test_restart_keeps_the_snapshot_and_recrawl_collects_again(self):
        self.fake.gate = True
        self.update()
        pending = self.state()["pending"]
        with patch("src.workflows.bilingual.datetime") as clock:
            clock.now.return_value.strftime.return_value = "restart"
            clock.now.return_value.isoformat.return_value = "restart"
            self.update("--restart")
        restarted = self.state()["pending"]
        self.assertEqual(restarted["snapshot"], pending["snapshot"])
        self.assertNotEqual(restarted["run"], pending["run"])
        self.assertEqual(len(self.collections), 1)

        with patch("src.workflows.bilingual.datetime") as clock:
            clock.now.return_value.strftime.return_value = "recrawl"
            clock.now.return_value.isoformat.return_value = "recrawl"
            self.update("--recrawl")
        self.assertEqual(len(self.collections), 2)
        self.assertNotEqual(self.state()["pending"]["snapshot"], pending["snapshot"])

    def old_epub(self, english: str) -> Path:
        from src.workflows.bilingual import write_bilingual
        from src.workflows.ingest import OutputOptions

        built, epub = self.root / "old", self.root / "old.epub"
        write_source(built, [english])
        write_json(
            built / "translations/01.json",
            {"translations": [{"index": 0, "zh": "门开了。"}]},
        )
        write_bilingual(
            built,
            built / "translations",
            OutputOptions(output=epub, output_formats=("epub",)),
        )
        return epub

    def seed(self, epub: Path, *args: str) -> tuple[int, dict]:
        with patch("builtins.print") as printed:
            code = bilingual_main(
                ["seed", "fake_book", "--from-epub", str(epub), *args]
            )
        return code, json.loads(printed.call_args_list[-1].args[0])

    def test_seed_recovers_matching_chapters_that_update_reuses(self):
        epub = self.old_epub("The door opened.")
        code, seeded = self.seed(epub)
        self.assertEqual(code, 0)
        self.assertEqual((seeded["seeded"], seeded["to_translate"]), (["01"], {}))
        recovered = json.loads(
            (self.root / seeded["baseline_run"] / "translations/01.json").read_text()
        )
        self.assertEqual(
            recovered["groups"], [{"english_indices": [0], "paragraphs": ["门开了。"]}]
        )

        code, updated = self.update()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.collections), 1)
        self.assertEqual(updated["snapshot"], seeded["snapshot"])
        self.assertEqual(
            self.fake.baselines[0].run_dir, self.root / seeded["baseline_run"]
        )

        code, refused = self.seed(epub)
        self.assertEqual((code, refused["status"]), (1, "failed"))
        self.assertIn("--replace", refused["error"])

    def test_seed_leaves_chapters_with_changed_english_to_translate(self):
        code, seeded = self.seed(self.old_epub("The door closed."))
        self.assertEqual(code, 0)
        self.assertEqual(seeded["seeded"], [])
        self.assertEqual(seeded["to_translate"], {"01": "English differs"})

    def test_run_directory_is_bound_to_one_method(self):
        self.update()
        run = self.root / self.state()["baseline"]["run"]
        record = json.loads((run / "bilingual_run.json").read_text())
        self.assertEqual(record["method"], "fake")
        spec = self.root / "book_specs/fake_book/config.json"
        config = json.loads(spec.read_text())
        write_json(spec, {**config, "translation": {"method": "neutral"}})
        with patch("builtins.print") as printed:
            code = bilingual_main(
                ["validate", str(run), "--book", "fake_book"]
            )
        result = json.loads(printed.call_args_list[-1].args[0])
        self.assertEqual((code, result["status"]), (1, "failed"))
        self.assertIn("translated with fake", result["error"])


if __name__ == "__main__":
    unittest.main()
