from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from experiments.iteration6 import probe
from experiments.iteration6 import resume


class ParallelWordingProbeTests(unittest.TestCase):
    def test_spine_paragraphs_preserve_text_and_exclude_headings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("a.xhtml", '<html><body><p class="P_Chapter_Header">Chapter 1</p>'
                    '<p>A <i>quiet</i> room.<sup>2</sup></p></body></html>')
                archive.writestr("b.xhtml", '<html><body><div>[Chapter 2]</div>'
                    '<div><span>A door </span><span>opened.</span></div></body></html>')
            rows = probe.chapter_paragraphs({"en_epub_path": str(path), "en_members": ["a.xhtml", "b.xhtml"]})
        self.assertEqual([x["english"] for x in rows], ["A quiet room.", "A door opened."])
        self.assertEqual([x["member"] for x in rows], ["a.xhtml", "b.xhtml"])

    def test_window_partition_does_not_drop_or_duplicate_tail(self) -> None:
        rows = [{"index": i, "english": "word " * n} for i, n in enumerate([130, 130, 170, 100, 40])]
        result = probe.windows(rows)
        self.assertEqual([[x["index"] for x in w] for w in result], [[0, 1], [2, 3, 4]])

    def test_generation_payload_cannot_inherit_target_gold(self) -> None:
        sample = {"sample_id": "dev", "title": "invented", "english": [{"index": 0, "english": "A door opened.", "chinese": "SECRET"}],
                  "context_before": [], "context_after": [], "gold": "SECRET", "paragraphs": ["SECRET"]}
        with patch.object(probe, "read", return_value={"examples": []}):
            payload = probe.base_payload(sample)
        self.assertNotIn("SECRET", str(payload))
        self.assertEqual(payload["english"], [{"index": 0, "english": "A door opened."}])

    def test_binding_rejects_changed_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input"
            source.write_text("original")
            manifest = Path(directory) / "manifest.json"
            probe.write(manifest, {"bindings": {str(source): probe.sha(source)}})
            probe.verify_bindings(manifest)
            source.write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "Frozen input changed"):
                probe.verify_bindings(manifest)

    def test_resume_does_not_overwrite_curated_admissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bank_manifest.json").write_text("{}")
            curated = root / "curated.json"
            curated.write_text("third reviewer rejected a previous admission")
            with patch.object(probe, "ROOT", root), patch.object(probe, "verify_bindings"), \
                    patch.object(probe, "main") as run, patch("sys.argv", ["resume", "mine"]):
                resume.main()
            run.assert_not_called()
            self.assertEqual(curated.read_text(), "third reviewer rejected a previous admission")

    def test_resume_rejects_changed_frozen_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "output_manifest.json").write_text("{}")
            with patch.object(probe, "ROOT", root), \
                    patch.object(probe, "verify_bindings", side_effect=RuntimeError("changed")), \
                    patch.object(probe, "main") as run, patch("sys.argv", ["resume", "generate"]):
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    resume.main()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
