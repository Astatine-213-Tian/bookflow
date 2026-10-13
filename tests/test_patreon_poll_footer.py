from __future__ import annotations

import copy
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

URL = "https://www.patreon.com/ViaLactea/posts/chapter-035-171588589"
INTRO = "Let’s take a break today."
QUESTION = "The war with Yngvarr is coming! How are you feeling about it?"
DIVIDER = {"type": "horizontalRule", "attrs": {"fallback_strategy": "ignore"}}


def node(text: str, *, bold: bool = False) -> dict:
    return {
        "type": "paragraph",
        "attrs": {"nodeTextAlignment": "center" if bold else "left"},
        "content": [
            {"type": "text", "text": text, "marks": [{"type": "bold"}] if bold else []}
        ],
    }


def post_document(tail: list[dict]) -> dict:
    return {
        "type": "doc",
        "content": [
            node("The door opened."),
            DIVIDER,
            node("The story continued."),
            *tail,
        ],
    }


def parse_document(document: dict, *, plain_html: str | None = None):
    attrs = {
        "title": "Chapter 035—Lamplight",
        "content_json_string": json.dumps(document),
    }
    if plain_html is not None:
        attrs["content"] = plain_html
    payload = {"data": {"type": "post", "attributes": attrs}}
    original = copy.deepcopy(payload)
    chapter = patreon._chapter_from_post(
        patreon.PostRef("171588589", attrs["title"], URL), payload
    )
    assert payload == original, "Raw post evidence was modified"
    return chapter


class PatreonPollFooterTests(unittest.TestCase):
    def test_parser_removes_intro_question_and_divider_from_both_representations(self):
        for tail in (
            [DIVIDER, node(QUESTION, bold=True)],
            [DIVIDER, node(INTRO, bold=True), node(QUESTION, bold=True)],
            [DIVIDER, node(INTRO, bold=True), node(QUESTION, bold=True), node(" ")],
        ):
            with self.subTest(tail=tail):
                chapter = parse_document(post_document(tail))
                self.assertEqual(
                    chapter.paragraphs, ["The door opened.", "The story continued."]
                )
                self.assertEqual(
                    chapter.html_blocks,
                    ["<p>The door opened.</p>", "<hr/>", "<p>The story continued.</p>"],
                )

    def test_html_text_candidate_and_rich_json_are_trimmed_together(self):
        document = post_document(
            [DIVIDER, node(INTRO, bold=True), node(QUESTION, bold=True)]
        )
        html = "".join(patreon._extract_json_html_blocks(document))
        chapter = parse_document(document, plain_html=html)
        self.assertEqual(
            chapter.paragraphs, ["The door opened.", "The story continued."]
        )
        self.assertNotIn(INTRO, "".join(chapter.html_blocks))

    def test_story_sections_and_author_notes_are_preserved(self):
        for tail in (
            [node(QUESTION, bold=True)],
            [DIVIDER, node("Where was he?")],
            [DIVIDER, node("“Where are you?”", bold=True)],
            [DIVIDER, node("An author's note.", bold=True)],
            [DIVIDER, node(QUESTION, bold=True), node("The story continues.")],
            [DIVIDER, node(QUESTION, bold=True), DIVIDER, node("The story continues.")],
        ):
            with self.subTest(tail=tail):
                document = post_document(tail)
                chapter = parse_document(document)
                self.assertEqual(
                    chapter.paragraphs, patreon._extract_json_paragraphs(document)
                )
                self.assertEqual(
                    chapter.html_blocks, patreon._extract_json_html_blocks(document)
                )
        standalone = {"type": "doc", "content": [DIVIDER, node(QUESTION, bold=True)]}
        self.assertEqual(parse_document(standalone).paragraphs, [QUESTION])

    def test_disagreement_does_not_silently_trim_story_paragraphs(self):
        document = post_document([DIVIDER, node(QUESTION, bold=True)])
        with self.assertRaisesRegex(ValueError, "plain and rich content"):
            parse_document(document, plain_html="<p>A different ending.</p>")

    def test_collection_saves_clean_source_and_retains_raw_evidence(self):
        document = post_document(
            [DIVIDER, node(INTRO, bold=True), node(QUESTION, bold=True)]
        )

        class PollFetcher(FixtureFetcher):
            async def get_json(self, url):
                data = await super().get_json(url)
                if data.get("data", {}).get("type") == "post":
                    attrs = data["data"]["attributes"]
                    attrs.pop("content", None)
                    attrs["content_json_string"] = json.dumps(document)
                return data

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(patreon, "PatreonFetcher", PollFetcher),
        ):
            path = collect_source(
                "10",
                Path(temporary) / "crawl",
                provider="patreon",
                options=CrawlOptions(language="en", concurrency=1),
            )
            book = json.loads(path.read_text())
            self.assertEqual(
                book["chapters"]["1001"]["blocks"],
                [
                    paragraph("The door opened."),
                    {"kind": "divider", "runs": []},
                    paragraph("The story continued."),
                ],
            )
            evidence = json.loads((path.parent / "evidence.json").read_text())
            self.assertEqual(
                json.loads(
                    evidence["posts"]["1001"]["data"]["attributes"][
                        "content_json_string"
                    ]
                ),
                document,
            )
