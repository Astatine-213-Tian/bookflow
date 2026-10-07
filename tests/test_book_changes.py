from __future__ import annotations

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from notion_books import NotionBooks, content_signature
from tests.notion_api import BlockAPI, SOURCE, write
import uuid

from src.content.changes import apply_changes, content_hash
from src.content.contract import validate_book
from src.content.models import Chapter, Volume
from src.notion.update import apply_update, read_current
from src.notion.upload import STORAGE
from src.runtime.files import write_json
from tests.fixtures import paragraph, prepared_crawl


def book():
    return prepared_crawl(
        title="书",
        author="作者",
        source_url="https://example.org/book",
        volumes=[
            Volume(
                "",
                [
                    Chapter("第1章", ["第一段。", "第二段。"]),
                    Chapter("第2章", ["编辑后的其他章节。"]),
                ],
            )
        ],
    )


def change(source, op):
    return {
        "version": 1,
        "id": "task-1",
        "book_id": source["identifier"],
        "operations": [op],
    }


class ChangesTests(unittest.TestCase):
    def test_explicit_author_correction_replaces_inherited_creator_list(self):
        source = book()
        source["metadata"].update(creator="A", creators=["A", "B"])
        task = change(
            source,
            {
                "kind": "metadata",
                "expected_sha256": content_hash({"creator": "A"}),
                "fields": {"creator": "C"},
            },
        )
        result, _ = apply_changes(source, task)
        self.assertEqual(result["metadata"]["creator"], "C")
        self.assertNotIn("creators", result["metadata"])
        self.assertEqual(source["metadata"]["creators"], ["A", "B"])

    def test_local_update_persists_findings_and_invalidates_stale_preparation(self):
        from src.content.prepared import save_source
        from src.workflows.update import update_book

        source = book()
        task = change(
            source,
            {
                "kind": "append_extra",
                "chapter_id": "bonus",
                "chapter": {"title": "番外", "blocks": [paragraph("ＭＳＮ")]},
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path, change_path = root / "input.json", root / "request.json"
            save_source(source, input_path)
            write_json(change_path, task)
            with patch(
                "src.workflows.update.preparation_fingerprint", return_value="rules-1"
            ):
                candidate = update_book(input_path, change_path, root / "result")
                self.assertEqual(
                    update_book(input_path, change_path, root / "result"), candidate
                )
            report = json.loads((candidate.parent / "report.json").read_text())
            self.assertGreater(report["normalization"]["total_changes"], 0)
            self.assertEqual(json.loads(input_path.read_text()), source)
            with (
                patch(
                    "src.workflows.update.preparation_fingerprint",
                    return_value="rules-2",
                ),
                self.assertRaisesRegex(ValueError, "fresh run"),
            ):
                update_book(input_path, change_path, root / "result")

    def test_replacement_preserves_omitted_metadata_and_reports_normalization(self):
        source = book()
        key = "chapter-1-1"
        source["chapters"][key].update(
            role="afterword", source={"id": "post-1", "url": "https://example.org/1"}
        )
        task = change(
            source,
            {
                "kind": "replace_chapter",
                "chapter_id": key,
                "expected_sha256": content_hash(source["chapters"][key]),
                "chapter": {"title": "后记", "blocks": [paragraph("ＭＳＮ")]},
            },
        )
        result, report = apply_changes(source, task)
        self.assertEqual(result["chapters"][key]["role"], "afterword")
        self.assertEqual(
            result["chapters"][key]["source"], source["chapters"][key]["source"]
        )
        self.assertGreater(report["total_changes"], 0)

    def test_replacement_keeps_other_chapters_and_refuses_stale_target(self):
        source = book()
        original = copy.deepcopy(source)
        key = "chapter-1-1"
        replacement = copy.deepcopy(source["chapters"][key])
        replacement["blocks"][1] = paragraph("新的ＭＳＮ段落。")
        task = change(
            source,
            {
                "kind": "replace_chapter",
                "chapter_id": key,
                "expected_sha256": content_hash(source["chapters"][key]),
                "chapter": replacement,
            },
        )
        result, _ = apply_changes(source, task)
        self.assertEqual(source, original)
        self.assertEqual(
            result["chapters"]["chapter-1-2"], source["chapters"]["chapter-1-2"]
        )
        self.assertEqual(
            result["chapters"][key]["blocks"][0], source["chapters"][key]["blocks"][0]
        )
        self.assertEqual(
            result["chapters"][key]["blocks"][1]["runs"][0]["text"], "新的 MSN 段落。"
        )
        source["chapters"][key]["blocks"].append(paragraph("后来手改。"))
        with self.assertRaisesRegex(ValueError, "changed"):
            apply_changes(source, task)

    def test_append_extra_is_idempotent_and_chapter_anchor_is_explicit(self):
        source = book()
        extra = {
            "title": "番外",
            "blocks": [paragraph("补充。")],
            "related_works": ["other-work"],
        }
        task = change(
            source, {"kind": "append_extra", "chapter_id": "bonus-1", "chapter": extra}
        )
        result, _ = apply_changes(source, task)
        self.assertEqual(apply_changes(result, task)[0], result)
        self.assertEqual(result["chapters"], source["chapters"])
        self.assertEqual(result["extras"][0]["related_works"], ["other-work"])
        task = change(
            source,
            {
                "kind": "append_chapter",
                "chapter_id": "new",
                "after": "chapter-1-1",
                "chapter": extra,
            },
        )
        self.assertEqual(
            apply_changes(source, task)[0]["sections"],
            [{"member": "chapter-1-1"}, {"member": "new"}, {"member": "chapter-1-2"}],
        )
        task["operations"][0]["after"] = "not-a-chapter"
        with self.assertRaisesRegex(ValueError, "anchor"):
            apply_changes(source, task)

    def test_schema_rejects_unknown_fields_and_unsafe_ids(self):
        for edit in ("unknown", "path", "missing", "duplicate"):
            source = book()
            if edit == "unknown":
                source["chapters"]["chapter-1-1"]["unexpected"] = "lost?"
            elif edit == "path":
                source["chapters"]["../chapter"] = source["chapters"].pop("chapter-1-1")
            elif edit == "missing":
                source["sections"] = []
            else:
                source["sections"].append({"member": "chapter-1-1"})
            with self.assertRaises(ValueError):
                validate_book(source)


class NotionChangesTests(unittest.IsolatedAsyncioTestCase):
    async def fixture(self):
        source = book()
        api = BlockAPI()
        for chapter in source["chapters"].values():
            id = str(uuid.uuid4())
            api.add_page(id, chapter["title"])
            await write(NotionBooks(api=api), chapter["blocks"], id)
            chapter.update(page_id=id, verified=True)
        source.update(
            storage=STORAGE, catalog_id=SOURCE, work_id=str(uuid.uuid4()), uploaded=True
        )
        return source, api

    async def test_resume_after_body_write_preserves_identity_and_later_edits(self):
        source, api = await self.fixture()
        key = "chapter-1-1"
        id = source["chapters"][key]["page_id"]
        other = source["chapters"]["chapter-1-2"]["page_id"]
        before = await read_current(source, tools=api)
        target = {"title": "第1章 修订", "blocks": [paragraph("修订。")]}
        task = change(
            source,
            {
                "kind": "replace_chapter",
                "chapter_id": key,
                "expected_sha256": content_hash(before["chapters"][key]),
                "chapter": target,
            },
        )
        original_call = api.call_api
        fail = True

        async def call(request):
            nonlocal fail
            result = await original_call(request)
            if (
                request["method"] == "PATCH"
                and request["path"] == "pages/" + id
                and fail
            ):
                fail = False
                raise TimeoutError("lost title response")
            return result

        api.call_api = call
        config = {"databases": {"works": {"data_source_id": SOURCE}}}
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "import.json"
            write_json(state, source)
            other_before = await NotionBooks(api=api).document(other)
            with self.assertRaises(ValueError):
                await apply_update(state, task, config, tools=api)
            mutations = api.mutations
            result = await apply_update(state, task, config, tools=api)
            self.assertEqual(api.mutations, mutations)
            self.assertEqual(result["chapters"][key]["title"], target["title"])
            self.assertEqual(
                content_signature((await NotionBooks(api=api).document(other)).blocks),
                content_signature(other_before.blocks),
            )
            await write(NotionBooks(api=api), [paragraph("后来手改。")], id)
            mutations = api.mutations
            result = await apply_update(state, task, config, tools=api)
            self.assertEqual(api.mutations, mutations)
            self.assertEqual(
                result["chapters"][key]["blocks"][0]["runs"][0]["text"], "后来手改。"
            )

    async def test_resume_interrupted_append_uses_existing_checkpoint(self):
        source, api = await self.fixture()
        calls = []
        new_id = str(uuid.uuid4())

        async def upload(checkpoint, state, config, *, tools):
            item = checkpoint["chapters"]["new"]
            calls.append(item.get("page_id"))
            if len(calls) == 1:
                raise RuntimeError("interrupted before create")
            api.add_page(new_id, item["title"])
            await write(NotionBooks(api=api), item["blocks"], new_id)
            item.update(page_id=new_id, verified=True)
            checkpoint["uploaded"] = True
            write_json(state, checkpoint)

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.update.upload_draft", upload),
        ):
            state = Path(temporary) / "import.json"
            write_json(state, source)
            task = change(
                source,
                {
                    "kind": "append_chapter",
                    "chapter_id": "new",
                    "after": "chapter-1-2",
                    "chapter": {"title": "第3章", "blocks": [paragraph("新章。")]},
                },
            )
            config = {"databases": {"works": {"data_source_id": SOURCE}}}
            with self.assertRaises(RuntimeError):
                await apply_update(state, task, config, tools=api)
            await apply_update(state, task, config, tools=api)
            self.assertEqual(calls, [None, None])
            self.assertEqual(
                json.loads(state.read_text())["chapters"]["new"]["page_id"], new_id
            )
