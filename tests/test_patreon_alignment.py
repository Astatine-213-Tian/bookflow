from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.crawler.models import CrawlOptions
from src.crawler.providers.patreon import parser as patreon
from src.workflows.collect import collect_source
from tests.fixtures import paragraph
from tests.test_collection import FixtureFetcher


def node(text: str, alignment: str | None = None) -> dict:
    result = {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    if alignment:
        result["attrs"] = {"nodeTextAlignment": alignment}
    return result


DOCUMENT = {
    "type": "doc",
    "content": [
        node("The door opened.", "left"),
        node("***", "center"),
        node("Who is Chamon?", "center"),
        node("The story continued."),
        node("* * *"),
        node("—Signed", "right"),
    ],
}


class PatreonAlignmentTests(unittest.TestCase):
    def test_source_keeps_the_alignment_patreon_stores_per_block(self):
        class AlignedFetcher(FixtureFetcher):
            async def get_json(self, url):
                data = await super().get_json(url)
                if data.get("data", {}).get("type") == "post":
                    attrs = data["data"]["attributes"]
                    attrs.pop("content", None)
                    attrs["content_json_string"] = json.dumps(DOCUMENT)
                return data

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(patreon, "PatreonFetcher", AlignedFetcher),
        ):
            path = collect_source(
                "10",
                Path(temporary) / "crawl",
                provider="patreon",
                options=CrawlOptions(language="en", concurrency=1),
            )
            blocks = json.loads(path.read_text())["chapters"]["1001"]["blocks"]

        self.assertEqual(
            blocks,
            [
                paragraph("The door opened."),
                {**paragraph("***"), "alignment": "center"},
                {**paragraph("Who is Chamon?"), "alignment": "center"},
                paragraph("The story continued."),
                paragraph("***"),
                {**paragraph("—Signed"), "alignment": "right"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
