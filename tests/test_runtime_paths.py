from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import chdir
from pathlib import Path
from unittest.mock import patch

from src.content.models import Chapter, Volume
from src.runtime.paths import WORK_ROOT_ENV, repo_root, work_root
from src.workflows.ingest import OutputOptions, prepare_and_write
from tests.fixtures import prepared_crawl


class WorkRootTests(unittest.TestCase):
    def test_working_data_follows_the_checkout_not_the_current_directory(self):
        with (
            tempfile.TemporaryDirectory() as elsewhere,
            chdir(elsewhere),
            patch.dict(os.environ, {}, clear=False) as environ,
        ):
            environ.pop(WORK_ROOT_ENV, None)
            self.assertEqual(work_root(), repo_root())

    def test_override_places_ingest_runs_under_the_work_root(self):
        with (
            tempfile.TemporaryDirectory() as root,
            tempfile.TemporaryDirectory() as elsewhere,
            chdir(elsewhere),
            patch.dict(os.environ, {WORK_ROOT_ENV: root}),
            patch("src.workflows.prepare.enrich_source", return_value={}),
        ):
            book = prepared_crawl(
                title="书",
                author="作者",
                volumes=[Volume("正文", [Chapter("第1章", ["内容。"])])],
                source_url="https://example.org/book",
            )
            result = prepare_and_write(
                book, OutputOptions(txt_output=Path(root) / "book.txt")
            )
            self.assertTrue(
                result.source_path.is_relative_to(
                    Path(root).resolve() / "generated" / "ingest"
                )
            )
            self.assertFalse((Path(elsewhere) / "generated").exists())


if __name__ == "__main__":
    unittest.main()
