from __future__ import annotations

import copy
import json
import posixpath
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from lxml import etree as ET
from notion_books import FIELDS

from src.content.contract import validate_book
from src.epub.writer import export_local
from src.notion.content import checkpoint_page_ids, localize_chapter_links
from src.notion.update import read_current


def unit(title: str, page_id: str, targets: list[str], *, extra=False) -> dict:
    return {
        "title": title,
        "role": "extra" if extra else "chapter",
        "page_id": page_id,
        "blocks": [
            {
                "kind": "paragraph",
                "runs": [
                    {"text": title + " ", "styles": []},
                    *[
                        {
                            "text": f"Link {index}",
                            "styles": ["italic"],
                            "href": "https://www.notion.so/" + target,
                        }
                        for index, target in enumerate(targets)
                    ],
                ],
            }
        ],
    }


def checkpoint() -> dict:
    main, first, second = "a" * 32, "b" * 32, "c" * 32
    return {
        "version": 3,
        "identifier": "fixture",
        "metadata": {"title": "Book", "creator": "Author", "language": "en"},
        "sections": [{"member": "main"}],
        "chapters": {"main": unit("Main", main, [first])},
        "extras": [
            {**unit("First extra", first, [main, second], extra=True), "id": "1"},
            unit("Second extra", second, [first], extra=True),
        ],
    }


def hrefs(chapter: dict) -> list[str]:
    return [
        run["href"]
        for block in chapter["blocks"]
        for run in block["runs"]
        if run.get("href")
    ]


class ExtraReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def read_fixture(self):
        saved = checkpoint()
        pages = {}
        for chapter in [*saved["chapters"].values(), *saved["extras"]]:
            title_field = FIELDS[
                "extra_title" if chapter["role"] == "extra" else "chapter_title"
            ]
            pages[chapter["page_id"]] = SimpleNamespace(
                properties={title_field: chapter["title"]},
                blocks=copy.deepcopy(chapter["blocks"]),
            )

        class Reader:
            def __init__(self, *args, **kwargs):
                pass

            async def document(self, page_id):
                return copy.deepcopy(pages[page_id])

        with patch("src.notion.update.NotionBooks", Reader):
            return await read_current(
                saved, tools=SimpleNamespace(call_api=None)
            ), saved

    async def test_readback_localizes_links_among_chapters_and_extras(self):
        book, saved = await self.read_fixture()
        validate_book(book)
        main = book["chapters"]["main"]
        first, second = book["extras"]
        main_id, first_id, second_id = (
            unit["blocks"][0]["anchor"] for unit in [main, first, second]
        )
        self.assertEqual(hrefs(main), ["#" + first_id])
        self.assertEqual(hrefs(first), ["#" + main_id, "#" + second_id])
        self.assertEqual(hrefs(second), ["#" + first_id])
        self.assertEqual(len(checkpoint_page_ids(saved)), 3)
        serialized = json.dumps(book)
        self.assertNotIn("page_id", serialized)
        for page_id in checkpoint_page_ids(saved).values():
            self.assertNotIn(page_id, serialized)
        again, _ = await self.read_fixture()
        self.assertEqual(book, again)

    async def test_exported_epub_resolves_all_extra_destinations(self):
        book, _ = await self.read_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.epub"
            export_local(book, path)
            with ZipFile(path) as archive:
                documents = {
                    name: ET.fromstring(archive.read(name))
                    for name in archive.namelist()
                    if name.endswith(".xhtml")
                }
                count = 0
                for name, document in documents.items():
                    for link in document.xpath('//*[local-name()="a"][@href]'):
                        href = link.get("href")
                        if "#" not in href:
                            continue
                        member, anchor = href.split("#", 1)
                        destination = (
                            posixpath.normpath(
                                posixpath.join(posixpath.dirname(name), member)
                            )
                            if member
                            else name
                        )
                        self.assertEqual(
                            len(
                                documents[destination].xpath(
                                    "//*[@id=$anchor]", anchor=anchor
                                )
                            ),
                            1,
                        )
                        count += 1
                self.assertEqual(count, 4)

    def test_empty_linked_extra_is_rejected_and_unrelated_link_stays_external(self):
        saved = checkpoint()
        saved["extras"][0]["blocks"] = []
        with self.assertRaisesRegex(ValueError, "no content"):
            localize_chapter_links(saved, checkpoint_page_ids(saved))
        saved = checkpoint()
        unknown = "https://www.notion.so/" + "d" * 32
        saved["extras"][0]["blocks"][0]["runs"].append(
            {"text": "Unrelated", "styles": [], "href": unknown}
        )
        localize_chapter_links(saved, checkpoint_page_ids(saved))
        self.assertEqual(hrefs(saved["extras"][0])[-1], unknown)


if __name__ == "__main__":
    unittest.main()
