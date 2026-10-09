"""In-memory official REST boundary for manuscript integration tests."""

from __future__ import annotations

import asyncio
import copy
import uuid
from urllib.parse import urlsplit
from notion_books import NotionBooks

PAGE = "11111111-1111-4111-8111-111111111111"
SOURCE = "22222222-2222-4222-8222-222222222222"


def paragraphs(text):
    return [
        {"kind": "paragraph", "runs": [{"text": line, "styles": []}]}
        for line in text.split("\n")
    ]


class BlockAPI:
    def __init__(self):
        self.pages = {}
        self.children = {}
        self.nodes = {}
        self.calls = []
        self.mutations = 0
        self.lose_reply = None
        self.add_page(PAGE)

    def add_page(
        self, page_id, title="Example", source=SOURCE, property="章节", properties=None
    ):
        self.pages[page_id] = {
            "object": "page",
            "id": page_id,
            "parent": {"data_source_id": source},
            "last_edited_time": "0",
            "properties": {
                property: {"type": "title", "title": [{"plain_text": title}]},
                **(properties or {}),
            },
        }
        self.children.setdefault(page_id, [])

    async def call_api(self, request):
        return await self(request)

    async def call(self, name, arguments):
        if name == "notion-create-pages":
            row = arguments["pages"][0]
            id = str(uuid.uuid4())
            property, title = next(iter(row["properties"].items()))
            source = arguments["parent"]["data_source_id"]
            self.add_page(id, title, source, property)
            return {"pages": [{"id": id}]}
        raise AssertionError((name, arguments))

    def _create(self, payload):
        node = copy.deepcopy(payload)
        node["object"] = "block"
        node["id"] = str(uuid.uuid4())
        kind = node["type"]
        nested = node[kind].pop("children", [])
        node["has_children"] = bool(nested)
        self.nodes[node["id"]] = node
        self.children[node["id"]] = [self._create(child) for child in nested]
        return node["id"]

    async def __call__(self, request):
        self.calls.append(copy.deepcopy(request))
        method, path = request["method"], urlsplit(request["path"]).path
        parts = path.split("/")
        if method == "GET" and parts[0] == "pages":
            body = self.pages[parts[1]]
        elif method == "GET" and parts[0] == "blocks":
            body = {
                "object": "list",
                "results": [
                    self.nodes[id]
                    for id in self.children[parts[1]]
                    if not self.nodes[id].get("archived")
                ],
                "has_more": False,
                "next_cursor": None,
            }
        else:
            self.mutations += 1
            if method == "POST" and path == "pages":
                payload = request["json"]
                id = str(uuid.uuid4())
                props = {
                    name: {"type": next(iter(value)), **copy.deepcopy(value)}
                    for name, value in payload["properties"].items()
                }
                title_field = next(name for name, value in props.items() if value["type"] == "title")
                title = "".join(run["text"]["content"] for run in props[title_field]["title"])
                self.add_page(id, title, payload["parent"]["data_source_id"], title_field, props)
                body = self.pages[id]
            elif method == "PATCH" and path.endswith("/children"):
                ids = [self._create(node) for node in request["json"]["children"]]
                self.children[parts[1]].extend(ids)
                body = {
                    "object": "list",
                    "results": [self.nodes[id] for id in ids],
                    "has_more": False,
                }
            elif method == "PATCH" and parts[0] == "pages":
                body = self.pages[parts[1]]
                for name, value in request["json"]["properties"].items():
                    kind = next(iter(value))
                    body["properties"][name] = {"type": kind, **copy.deepcopy(value)}
            elif method == "PATCH" and parts[0] == "blocks":
                self.nodes[parts[1]].update(copy.deepcopy(request["json"]))
                body = self.nodes[parts[1]]
            elif method == "DELETE" and parts[0] == "blocks":
                self.nodes[parts[1]]["archived"] = True
                body = self.nodes[parts[1]]
            else:
                raise AssertionError(request)
            for page in self.pages.values():
                page["last_edited_time"] = str(self.mutations)
            if self.lose_reply == self.mutations:
                raise TimeoutError("response lost after mutation")
        return {"status": 200, "body": copy.deepcopy(body)}


async def write(reader, blocks, page_id=PAGE, *, targets=None):
    plan = await reader.prepare_content(page_id, blocks, targets=targets or {})
    plan = await reader.write_content(plan, checkpoint=lambda plan: None)
    return await reader.document(page_id)


def roundtrip(blocks):
    async def run():
        api = BlockAPI()
        await write(NotionBooks(api=api), blocks)
        return (await NotionBooks(api=api).document(PAGE)).blocks

    return asyncio.run(run())
