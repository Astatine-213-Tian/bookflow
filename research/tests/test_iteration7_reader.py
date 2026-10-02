from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from experiments.iteration7 import reader


class ReadingFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "key": "new50/new_001", "sample_id": "new_001", "batch": "new50",
            "batch_manifest_sha256": "batch", "display_manifest_sha256": "display",
            "candidates": [{"id": c, "output_sha256": f"output-{c}", "text_sha256": f"text-{c}"}
                           for c in "ABCD"],
        }
        self.payload = {"sample_key": self.case["key"], "display_manifest_sha256": "display",
                        "choice": "preferred", "candidate_ids": ["B"], "note": "更自然"}

    def test_stale_page_invalid_ids_and_invalid_ties_are_rejected(self) -> None:
        for changes in ({"display_manifest_sha256": "old"}, {"candidate_ids": ["E"]},
                        {"candidate_ids": ["B", "B"]}, {"choice": "tie"},
                        {"choice": "none"}, {"note": "x" * 4001}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reader.validate_vote({**self.payload, **changes}, self.case)

    def test_revisions_persist_exact_outputs_and_keep_first_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(reader, "FEEDBACK", Path(directory)), \
                patch.object(reader, "dataset", return_value={"cases": [self.case]}):
            first = reader.save_vote(self.payload)
            last = reader.save_vote({**self.payload, "choice": "tie", "candidate_ids": ["A", "D"]})
            disk = reader.votes()["votes"][self.case["key"]]
            events = [json.loads(x) for x in (Path(directory) / "events.jsonl").read_text().splitlines()]
        self.assertEqual(disk, last)
        self.assertEqual(last["first_recorded_at"], first["first_recorded_at"])
        self.assertEqual(last["outputs"]["D"]["output_sha256"], "output-D")
        self.assertEqual([x["candidate_ids"] for x in events], [["B"], ["A", "D"]])

    def test_loopback_api_rejects_foreign_origin_before_writing(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), reader.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(reader, "FEEDBACK", Path(directory)), \
                    patch.object(reader, "dataset", return_value={"cases": [self.case]}):
                connection = HTTPConnection("127.0.0.1", server.server_port)
                body = json.dumps(self.payload)
                for origin, expected in (("https://outside.example", 403),
                                         (f"http://127.0.0.1:{server.server_port}", 200)):
                    connection.request("POST", "/api/vote", body,
                                       {"Content-Type": "application/json", "Origin": origin})
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    if expected == 403:
                        self.assertEqual(reader.votes()["votes"], {})
                connection.request("GET", "/api/export")
                exported = json.loads(connection.getresponse().read())
                self.assertEqual(exported["votes"][self.case["key"]]["candidate_ids"], ["B"])
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_highlights_ignore_punctuation_and_mark_local_wording(self) -> None:
        identical = ["他说：这里很好。", "他说，这里很好！"]
        self.assertEqual(reader.diff_ranges(identical), [[], []])
        texts = ["他把所有公文都办好了，随即出门。", "他把所有公文都处理妥当了，随即出门。"]
        ranges = reader.diff_ranges(texts)
        self.assertEqual(["".join(t[a:b] for a,b in r) for t,r in zip(texts,ranges)],
                         ["办好", "处理妥当"])

    def test_source_crop_is_literal_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reader.write(root / "samples/test.json", {"title": "书", "chapter": 1,
                                                        "english": [{"english": "The window."}]})
            gold = root / "gold/test.json"
            reader.write(gold, {"usable": True, "paragraphs": ["前文。目标。后文。"]})
            reader.write(root / "manifest.json", {})
            reader.write(root / "outputs/test/direct.json", {"paragraphs": ["译文。"]})
            crop = {"sample_id": "test", "gold_file_sha256": reader.sha(gold),
                    "start_character_in_first_paragraph": 3,
                    "end_character_exclusive_in_last_paragraph": 6, "paragraphs": ["目标。"]}
            path = root / "audit/display_crops.json"
            reader.write(path, {"records": [crop]})
            reader.CACHE.clear()
            case = reader.get_case(root, "test", "new50", 1, {"候选A": "direct"})
            self.assertEqual(case["author"], ["目标。"])
            reader.write(path, {"records": [{**crop, "paragraphs": ["重写。"]}]})
            with self.assertRaisesRegex(ValueError, "Nonliteral"):
                reader.get_case(root, "test", "new50", 1, {"候选A": "direct"})
            reader.write(path, {"records": [{**crop, "gold_file_sha256": "stale"}]})
            with self.assertRaisesRegex(ValueError, "Stale"):
                reader.get_case(root, "test", "new50", 1, {"候选A": "direct"})
        reader.CACHE.clear()


if __name__ == "__main__":
    unittest.main()
