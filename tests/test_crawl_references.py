from __future__ import annotations

import unittest

from src.content.contract import validate_book
from src.content.models import Chapter, Volume
from src.inputs.crawl import extract_crawl
from src.workflows.prepare import prepare_book


def crawl(chapters: list[Chapter], **kwargs) -> dict:
    return extract_crawl(
        title="Fixture",
        author="Author",
        source_url="https://example.com/books/book/",
        volumes=[Volume("正文", chapters)],
        **kwargs,
    )


def links(chapter: dict) -> list[str]:
    return [
        run["href"]
        for block in chapter["blocks"]
        for run in block["runs"]
        if "href" in run
    ]


class CrawlReferenceTests(unittest.TestCase):
    def test_relative_links_use_chapter_url_and_keep_external_destinations(self):
        book = crawl(
            [
                Chapter(
                    "Chapter",
                    source_url="https://example.com/chapters/one.html",
                    html_blocks=[
                        '<p><a href="../reference?q=1&amp;x=2#part">Relative</a> '
                        '<a href="/about">Root</a> '
                        '<a href="//cdn.example.com/a">Protocol relative</a> '
                        '<a href="https://elsewhere.test/p?x=1#part">External</a> '
                        '<a href="mailto:author@example.com">Mail</a></p>'
                    ],
                )
            ]
        )
        validate_book(book)
        self.assertEqual(
            links(book["chapters"]["chapter-1-1"]),
            [
                "https://example.com/reference?q=1&x=2#part",
                "https://example.com/about",
                "https://cdn.example.com/a",
                "https://elsewhere.test/p?x=1#part",
                "mailto:author@example.com",
            ],
        )

    def test_missing_chapter_url_uses_book_url_without_anchor_collisions(self):
        book = crawl(
            [
                Chapter("One", html_blocks=['<p id="intro"><a href="about">A</a></p>']),
                Chapter("Two", html_blocks=['<p id="intro">B</p>']),
            ]
        )
        validate_book(book)
        self.assertEqual(
            links(book["chapters"]["chapter-1-1"]),
            ["https://example.com/books/book/about"],
        )
        self.assertTrue(
            all(
                "anchor" not in b
                for ch in book["chapters"].values()
                for b in ch["blocks"]
            )
        )

    def test_local_footnotes_are_isolated_per_chapter_and_survive_preparation(self):
        body = (
            '<p id="body">Text <a role="doc-noteref" href="#note">1</a></p>'
            '<aside id="note" role="doc-footnote">1. Note '
            '<a role="doc-backlink" href="#body">back</a></aside>'
        )
        book = crawl(
            [Chapter("One", html_blocks=[body]), Chapter("Two", html_blocks=[body])]
        )
        book, _ = prepare_book(book)
        validate_book(book)
        all_anchors = []
        for ch in book["chapters"].values():
            body_block, note = ch["blocks"]
            self.assertEqual(note["footnote"], note["anchor"])
            self.assertEqual(
                links(ch), ["#" + note["anchor"], "#" + body_block["anchor"]]
            )
            all_anchors.extend([body_block["anchor"], note["anchor"]])
        self.assertEqual(len(set(all_anchors)), 4)

    def test_known_chapter_starts_and_anchors_become_portable_links(self):
        book = crawl(
            [
                Chapter(
                    "One",
                    source_url="https://example.com/chapters/one.html",
                    html_blocks=[
                        '<p><a href="two.html">Chapter two</a> '
                        '<a href="two.html#%E5%B0%BE">Its tail</a> '
                        '<a href="two.html#unknown">Website anchor</a></p>'
                    ],
                ),
                Chapter(
                    "Two",
                    source_url="https://example.com/chapters/two.html",
                    html_blocks=['<p>Opening.</p><p id="尾">Tail.</p>'],
                ),
            ]
        )
        validate_book(book)
        second = book["chapters"]["chapter-1-2"]["blocks"]
        self.assertEqual(
            links(book["chapters"]["chapter-1-1"]),
            [
                "#" + second[0]["anchor"],
                "#" + second[1]["anchor"],
                "https://example.com/chapters/two.html#unknown",
            ],
        )

    def test_absolute_note_urls_resolve_incoming_and_return_links(self):
        url = "https://example.com/chapter"
        book = crawl(
            [
                Chapter(
                    "One",
                    source_url=url,
                    html_blocks=[
                        f'<p id="body">Text <a href="{url}#%E6%B3%A8">1</a></p>'
                        f'<aside id="注" role="doc-footnote">Note <a href="{url}#body">back</a></aside>'
                    ],
                )
            ]
        )
        validate_book(book)
        chapter = book["chapters"]["chapter-1-1"]
        body, note = chapter["blocks"]
        self.assertEqual(note["footnote"], note["anchor"])
        self.assertEqual(links(chapter), ["#" + note["anchor"], "#" + body["anchor"]])
        self.assertEqual(body["runs"][-1]["link_role"], "noteref")
        self.assertEqual(note["runs"][-1]["link_role"], "backlink")

    def test_repeated_source_urls_do_not_guess_cross_chapter_targets(self):
        url = "https://example.com/shared"
        book = crawl(
            [
                Chapter("One", source_url=url, html_blocks=['<p id="part">One.</p>']),
                Chapter("Two", source_url=url, html_blocks=['<p id="part">Two.</p>']),
                Chapter(
                    "Three", html_blocks=[f'<p><a href="{url}#part">Source</a></p>']
                ),
            ]
        )
        validate_book(book)
        self.assertEqual(links(book["chapters"]["chapter-1-3"]), [url + "#part"])

    def test_broken_local_reference_is_not_silently_discarded(self):
        with self.assertRaisesRegex(ValueError, "cannot be resolved"):
            crawl(
                [Chapter("One", html_blocks=['<p><a href="#missing">Missing</a></p>'])]
            )

    def test_notes_without_backlinks_keep_return_anchors_for_preparation(self):
        book = crawl(
            [
                Chapter(
                    "One",
                    html_blocks=[
                        '<p id="r">Text<a role="doc-noteref" href="#n">1</a></p>'
                        '<aside id="n" role="doc-footnote">Note.</aside>'
                    ],
                )
            ]
        )
        body = book["chapters"]["chapter-1-1"]["blocks"][0]
        self.assertIn("anchor", body)
        prepared, _ = prepare_book(book)
        validate_book(prepared)
        chapter = prepared["chapters"]["chapter-1-1"]
        note = chapter["blocks"][-1]
        self.assertEqual(note["runs"][-1]["href"], "#" + body["anchor"])
        self.assertEqual(note["runs"][-1]["link_role"], "backlink")

    def test_reference_to_note_continuation_targets_complete_note(self):
        book = crawl(
            [
                Chapter(
                    "One",
                    html_blocks=[
                        '<p>Text<a role="doc-noteref" href="#continuation">1</a></p>'
                        '<aside id="n" role="doc-footnote"><p>First.</p>'
                        '<p id="continuation">Second.</p></aside>'
                    ],
                )
            ]
        )
        chapter = book["chapters"]["chapter-1-1"]
        note_id = chapter["blocks"][1]["footnote"]
        self.assertEqual(links(chapter), ["#" + note_id])
        prepared, _ = prepare_book(book)
        validate_book(prepared)
        blocks = prepared["chapters"]["chapter-1-1"]["blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[-1]["anchor"], note_id)
        self.assertIn(
            "First.\n\nSecond.", "".join(r["text"] for r in blocks[-1]["runs"])
        )
        self.assertEqual(blocks[-1]["runs"][-1]["href"], "#" + blocks[0]["anchor"])


if __name__ == "__main__":
    unittest.main()
