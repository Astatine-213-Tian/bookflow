from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from src.crawler.models import CrawlOptions
from src.crawler.providers.patreon import parser as patreon
from src.crawler.registry import find_parser
from src.crawler.search.orchestrator import search_all
from src.workflows.collect import collect_source
from src.workflows.ingest import OutputOptions, ingest
from tests.fixtures import isolated_workdir


class FixtureFetcher:
    instances = []
    fail_comments = False

    def __init__(self, **kwargs):
        self.requests = []
        self.stopped = False
        self.instances.append(self)

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def open_collection(self, url):
        pass

    async def get_json(self, url):
        self.requests.append(url)
        path = urlsplit(url).path
        if "/collection/" in path:
            cid = path.split("/")[-1]
            return {
                "data": {
                    "type": "collection",
                    "id": cid,
                    "attributes": {"title": "Book " + cid, "post_count": 1},
                    "relationships": {
                        "posts": {"data": [{"type": "post", "id": cid + "01"}]}
                    },
                },
                "included": [
                    {"type": "campaign", "attributes": {"name": "Creator " + cid}},
                    post(cid + "01"),
                    post("999"),
                ],
            }
        if path.endswith("/comments"):
            if self.fail_comments:
                raise RuntimeError("comments unavailable")
            comment = {
                "type": "comment",
                "id": "c1",
                "attributes": {"body": "Comment", "created": "2026-01-01"},
            }
            return {"data": [comment, comment], "links": {}}
        return {"data": post(path.split("/")[-1])}


def post(id):
    return {
        "type": "post",
        "id": id,
        "attributes": {
            "title": "Chapter 1",
            "published_at": "2020-01-01T00:00:00Z",
            "current_user_can_view": True,
            "content": "<p>Source " + id + "</p>",
        },
    }


class CollectionTests(unittest.TestCase):
    def test_cover_and_explicit_empty_membership_ignore_included_sidecars(self):
        data = {
            "data": {
                "attributes": {
                    "title": "Empty",
                    "post_count": 0,
                    "thumbnail": "https://example.org/cover.jpg",
                },
                "relationships": {"posts": {"data": []}},
            },
            "included": [post("999")],
        }
        meta, refs = patreon._parse_collection(data, "10")
        self.assertEqual(meta.cover_mime, "image/jpeg")
        self.assertEqual(refs, [])
        del data["data"]["relationships"]
        with self.assertRaisesRegex(ValueError, "membership"):
            patreon._parse_collection(data, "10")

    def test_nested_quote_preserves_paragraphs_and_emphasis(self):
        from src.inputs.html import read_html_blocks

        blocks = read_html_blocks(
            b"<html><body><blockquote><p>First <b>bold</b>.</p><p>Second.</p></blockquote><p>Outside.</p></body></html>",
            "quote.xhtml",
            {},
        )
        self.assertEqual([b["kind"] for b in blocks], ["quote", "quote", "paragraph"])
        self.assertEqual(blocks[0]["runs"][1], {"text": "bold", "styles": ["bold"]})
        self.assertEqual(blocks[1]["runs"][0]["text"], "Second.")

    def setUp(self):
        isolated_workdir(self)
        FixtureFetcher.instances = []
        FixtureFetcher.fail_comments = False

    def test_two_collections_share_provider_without_book_identity_or_feed_leakage(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(patreon, "PatreonFetcher", FixtureFetcher),
        ):
            for cid, language in [("10", "en"), ("20", "fr")]:
                path = collect_source(
                    cid,
                    Path(temporary) / cid,
                    provider="patreon",
                    options=CrawlOptions(
                        language=language, include_comments=True, concurrency=1
                    ),
                )
                book = json.loads(path.read_text())
                evidence = json.loads((path.parent / "evidence.json").read_text())
                self.assertEqual(book["metadata"]["title"], "Book " + cid)
                self.assertEqual(book["metadata"]["creator"], "Creator " + cid)
                self.assertEqual(book["metadata"]["language"], language)
                self.assertEqual(list(book["chapters"]), [cid + "01"])
                self.assertEqual(
                    book["chapters"][cid + "01"]["source"]["id"], cid + "01"
                )
                self.assertEqual(len(evidence["comments"][cid + "01"]), 1)
                self.assertEqual(evidence["comments_status"], "complete")
            self.assertTrue(all(f.stopped for f in FixtureFetcher.instances))
            self.assertFalse(
                any(
                    "/campaigns/" in url or "/999" in url
                    for f in FixtureFetcher.instances
                    for url in f.requests
                )
            )

    def test_direct_ingest_uses_same_collection_with_explicit_extra_and_overrides(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(patreon, "PatreonFetcher", FixtureFetcher),
        ):
            target = Path(temporary) / "book.txt"
            result = ingest(
                "10",
                parser=find_parser("10", "patreon"),
                crawl_options=CrawlOptions(
                    title="Override",
                    author="Writer",
                    language="en",
                    extra_post_ids=("777",),
                    concurrency=1,
                ),
                output_options=OutputOptions(txt_output=target),
            )
            self.assertEqual(result.txt_path, target)
            self.assertIn("Override", target.read_text())
            self.assertIn("Writer", target.read_text())
            self.assertIn("Source 1001", target.read_text())
            self.assertIn("Source 777", target.read_text())
            self.assertFalse(
                any("/comments" in url for url in FixtureFetcher.instances[0].requests)
            )

    def test_failed_comments_do_not_become_successful_empty_evidence(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(patreon, "PatreonFetcher", FixtureFetcher),
        ):
            FixtureFetcher.fail_comments = True
            with self.assertRaisesRegex(RuntimeError, "comments unavailable"):
                collect_source(
                    "10",
                    Path(temporary) / "run",
                    provider="patreon",
                    options=CrawlOptions(include_comments=True, concurrency=1),
                )
            self.assertFalse((Path(temporary) / "run/source.json").exists())
            self.assertTrue(FixtureFetcher.instances[0].stopped)

    def test_collection_only_provider_is_not_used_for_search(self):
        with patch("src.crawler.search.orchestrator.load_search_module") as load:
            with self.assertRaisesRegex(ValueError, "search"):
                search_all("Book", parser_name="patreon")
            load.assert_not_called()

    def test_locked_teaser_is_not_imported_as_a_chapter(self):
        ref = patreon.PostRef(
            "1", "Chapter", "https://www.patreon.com/posts/1", "", 0, False
        )
        with self.assertRaises(patreon.PatreonAuthError):
            patreon._chapter_from_post(ref, {"data": post("1")})
