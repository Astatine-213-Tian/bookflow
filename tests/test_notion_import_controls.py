from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from notion_books import NotionError

from src.notion.cms import STORAGE, ensure_views
from src.notion.mcp import finish_write
from src.notion.presentation import (
    attach_public_cover,
    ensure_volume_colors,
)
from src.notion.recovery import recover_template
from src.runtime.files import digest

WORK = "11111111-1111-1111-1111-111111111111"
DS = "22222222-2222-2222-2222-222222222222"
TEMPLATE = "33333333-3333-3333-3333-333333333333"


def book():
    return {
        "storage": STORAGE,
        "catalog_id": DS,
        "work_id": WORK,
        "chapters_data_source_id": DS,
        "chapters_view_id": "main",
        "sections": [
            {"title": "上卷", "children": [{"member": "one"}]},
            {"title": "尾声", "children": [{"member": "two"}]},
        ],
        "chapters": {"one": {}, "two": {}},
        "extras": [],
    }


class ImportControlsTests(unittest.IsolatedAsyncioTestCase):
    async def test_template_discovery_retries_only_truncated_reads(self):
        value = book()
        reader = SimpleNamespace(
            discover=AsyncMock(
                side_effect=[
                    NotionError(
                        {"operation": "discover", "code": "read", "uncertain": False},
                        "Notion response is truncated",
                    ),
                    {
                        "chapters_view": "main",
                        "chapters_data_source": DS,
                        "extras_view": "extra",
                    },
                ]
            )
        )
        config = {
            "databases": {
                "works": {"data_source_id": DS},
                "extras": {"data_source_id": DS},
            }
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.cms.NotionBooks", return_value=reader),
            patch("src.notion.cms.asyncio.sleep", new=AsyncMock()),
        ):
            await ensure_views(
                value, Path(temporary) / "state.json", config, tools=None
            )
            self.assertEqual(value["view_id"], "extra")
            reader.discover.side_effect = NotionError(
                {"operation": "discover", "code": "read", "uncertain": False},
                "permission denied",
            )
            with self.assertRaisesRegex(NotionError, "permission denied"):
                await ensure_views(
                    value, Path(temporary) / "state.json", config, tools=None
                )

    async def test_new_volume_colors_preserve_existing_options_and_resume(self):
        value = book()
        tools = SimpleNamespace(call=AsyncMock(return_value={}))
        before = {"用户标签": "brown"}
        after = before | {"上卷": "blue", "尾声": "green"}
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "src.notion.presentation.volume_options",
                new=AsyncMock(side_effect=[before, after, after, after]),
            ),
        ):
            state = Path(temporary) / "state.json"
            await ensure_volume_colors(value, state, tools=tools)
            await ensure_volume_colors(value, state, tools=tools)
        self.assertEqual(value["volume_colors"], {"上卷": "blue", "尾声": "green"})
        tools.call.assert_awaited_once()
        statement = tools.call.call_args.args[1]["statements"]
        self.assertIn("'用户标签':brown", statement)
        self.assertIn("'尾声':green", statement)

    async def test_uncertain_public_cover_write_is_not_repeated(self):
        value = book() | {
            "cover_url": "https://example.test/cover.png",
            "cover_sha256": digest(b"image"),
        }
        reader = SimpleNamespace(
            page=AsyncMock(return_value=SimpleNamespace(cover_known=True, cover=None))
        )
        tools = SimpleNamespace(
            call=AsyncMock(side_effect=ConnectionError("lost response"))
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.presentation.NotionBooks", return_value=reader),
        ):
            state = Path(temporary) / "state.json"
            with self.assertRaises(ConnectionError):
                await attach_public_cover(value, state, tools=tools)
            with self.assertRaisesRegex(ValueError, "uncertain"):
                await attach_public_cover(value, state, tools=tools)
        tools.call.assert_awaited_once()
        self.assertEqual(value["cover_pending"], value["cover_url"])

    async def test_existing_matching_cover_is_verified_without_a_write(self):
        value = book() | {
            "cover_url": "https://example.test/cover.png",
            "cover_sha256": digest(b"image"),
            "cover_pending": "prior write",
        }
        reader = SimpleNamespace(
            page=AsyncMock(
                return_value=SimpleNamespace(
                    cover_known=True, cover={"url": value["cover_url"]}
                )
            )
        )
        tools = SimpleNamespace(call=AsyncMock())
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.presentation.NotionBooks", return_value=reader),
            patch("src.notion.presentation.public_cover", return_value=b"image"),
        ):
            await attach_public_cover(
                value, Path(temporary) / "state.json", tools=tools
            )
        tools.call.assert_not_awaited()
        self.assertTrue(value["cover_uploaded"])
        self.assertNotIn("cover_pending", value)

    async def test_template_recovery_uses_mcp_once_and_preserves_pending_write(self):
        value = book()
        tools = SimpleNamespace(
            call=AsyncMock(side_effect=ConnectionError("lost response"))
        )
        reader = SimpleNamespace(
            page=AsyncMock(return_value=SimpleNamespace(data_source_id=DS, shell="")),
            catalog=AsyncMock(
                return_value={
                    "works": {
                        "default_template": "https://app.notion.com/p/"
                        + TEMPLATE.replace("-", "")
                    }
                }
            ),
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.recovery.NotionBooks", return_value=reader),
            patch("src.notion.recovery.ensure_views", new=AsyncMock()) as discover,
        ):
            state = Path(temporary) / "state.json"
            with self.assertRaises(ConnectionError):
                await recover_template(
                    value,
                    state,
                    {"databases": {"works": {"data_source_id": DS}}},
                    tools=tools,
                )
            await recover_template(
                value,
                state,
                {"databases": {"works": {"data_source_id": DS}}},
                tools=tools,
            )
        tools.call.assert_awaited_once_with(
            "notion-update-page",
            {
                "page_id": WORK,
                "command": "apply_template",
                "template_id": TEMPLATE,
                "allow_async": False,
            },
        )
        discover.assert_awaited_once()

    async def test_existing_template_content_only_runs_discovery(self):
        value = book()
        tools = SimpleNamespace(call=AsyncMock())
        reader = SimpleNamespace(
            page=AsyncMock(
                return_value=SimpleNamespace(
                    data_source_id=DS, shell="<database>正文</database>"
                )
            )
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("src.notion.recovery.NotionBooks", return_value=reader),
            patch("src.notion.recovery.ensure_views", new=AsyncMock()) as discover,
        ):
            await recover_template(
                value,
                Path(temporary) / "state.json",
                {"databases": {"works": {"data_source_id": DS}}},
                tools=tools,
            )
        tools.call.assert_not_awaited()
        discover.assert_awaited_once()

    async def test_async_template_completion_is_polled_without_repeating_write(self):
        tools = SimpleNamespace(
            call=AsyncMock(
                side_effect=[
                    {"object": "async_task", "id": "task", "status": "running"},
                    {"status": "running"},
                    {
                        "status": "succeeded",
                        "result": {"ok": True},
                    },
                ]
            )
        )
        with patch("src.notion.mcp.asyncio.sleep", new=AsyncMock()):
            self.assertEqual(
                await finish_write(
                    tools, "notion-update-page", {"command": "apply_template"}
                ),
                {"ok": True},
            )
        self.assertEqual(
            [c.args[0] for c in tools.call.call_args_list],
            ["notion-update-page", "notion-get-async-task", "notion-get-async-task"],
        )


if __name__ == "__main__":
    unittest.main()
