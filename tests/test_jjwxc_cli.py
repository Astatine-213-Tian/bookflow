from __future__ import annotations

import unittest
from typing import Any, cast

from src.cli.jjwxc import lookup
from src.metadata.catalog import SourceMetadata
from src.metadata.jjwxc import JjwxcChapter, JjwxcContents, JjwxcVolume


class FakeFinder:
    def __init__(self, result: SourceMetadata | None) -> None:
        self.result, self.packages = result, []

    def find(self, package):
        self.packages.append(package)
        return self.result


def metadata(provider: str = "jinjiang") -> SourceMetadata:
    contents = JjwxcContents(
        source="https://www.jjwxc.net/onebook.php?novelid=1",
        volumes=(
            JjwxcVolume("正文", (JjwxcChapter(1, "第 1 章", None),)),
            JjwxcVolume("后来", (JjwxcChapter(2, "某一天", None),)),
        ),
    )
    return SourceMetadata(
        provider=provider,
        title="书",
        author="作者",
        language="zh-CN",
        date="2019-01-01",
        source="https://www.jjwxc.net/onebook.php?novelid=1",
        description="",
        subjects=("科幻",),
        table_of_contents=contents,
    )


class JjwxcLookupTests(unittest.TestCase):
    def test_reports_official_volumes_for_title_and_author(self):
        finder = FakeFinder(metadata())
        result = lookup("书", "作者", finder=cast(Any, finder))
        self.assertEqual(
            (finder.packages[0].title, finder.packages[0].author), ("书", "作者")
        )
        self.assertEqual(
            [v["title"] for v in result["table_of_contents"]["volumes"]],
            ["正文", "后来"],
        )
        self.assertEqual(result["table_of_contents"]["chapter_count"], 2)

    def test_missing_or_non_jinjiang_match_fails(self):
        for found in (None, metadata("kadokado")):
            with self.assertRaisesRegex(ValueError, "No unique Jinjiang work"):
                lookup("书", "作者", finder=cast(Any, FakeFinder(found)))


if __name__ == "__main__":
    unittest.main()
