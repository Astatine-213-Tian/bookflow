"""In-memory official REST boundary for manuscript integration tests."""

from __future__ import annotations

import asyncio
import copy
import json
import uuid
from urllib.parse import unquote, urlsplit
from notion_books import PROPERTIES, NotionBooks

PAGE = "11111111-1111-4111-8111-111111111111"
SOURCE = "22222222-2222-4222-8222-222222222222"

# Current workspace names. Bookflow identifies properties by ID; these are what
# MCP payloads and REST responses show, and editors may rename them.
DISPLAY = {
    "chapters": {
        "title": "章节",
        "parent_title": "所属标题",
        "publish": "发布章节",
        "last_published": "上次发布（勿手动修改）",
        "publication_result": "发布结果（勿手动修改）",
        "content_status": "正文状态（勿手动修改）",
        "revision": "最近编辑（勿手动修改）",
    },
    "extras": {
        "title": "番外",
        "related_works": "涉及作品",
        "publish": "发布至收录书",
        "last_published": "上次发布（勿手动修改）",
        "publication_result": "发布结果（勿手动修改）",
        "content_status": "正文状态（勿手动修改）",
        "revision": "最近编辑",
    },
    "works": {
        "title": "作品",
        "authors": "作者",
        "subjects": "书籍分类",
        "series": "系列",
        "series_position": "系列序号",
        "language": "语言",
        "description": "简介",
        "source": "来源",
        "publication_date": "出版日期",
        "publish": "全书发布",
        "last_published": "上次发布（勿手动修改）",
        "publication_result": "发布结果（勿手动修改）",
        "book_binding": "Bookshelf 绑定（勿手动修改）",
    },
    "authors": {"title": "作者", "homepage": "作者主页"},
}


def display_names(kind, renamed=None):
    return DISPLAY[kind] | (renamed or {})


def schema_body(data_source, kind="chapters", renamed=None, omit=()):
    """The REST data source schema the SDK binds property IDs against."""
    names = display_names(kind, renamed)
    properties = {}
    for field, spec in PROPERTIES[kind].items():
        if field in omit:
            continue
        typ = "rich_text" if spec["type"] == "text" else spec["type"]
        properties[names[field]] = {"id": spec["id"], "name": names[field], "type": typ}
    return {"object": "data_source", "id": data_source, "properties": properties}


def mcp_schema(kind="chapters", renamed=None, omit=(), options=None, **state):
    """MCP's name-keyed data source state, as notion-fetch returns it."""
    names = display_names(kind, renamed)
    schema = {
        names[field]: {"type": spec["type"], "options": (options or {}).get(field, [])}
        for field, spec in PROPERTIES[kind].items()
        if field not in omit
    }
    return "<data-source-state>\n" + json.dumps(
        {"schema": schema, **state}, ensure_ascii=False
    ) + "\n</data-source-state>"


def schema_api(sources):
    """A REST transport serving only schemas; ``sources`` maps data source to kind."""

    async def api(request):
        path = request["path"]
        if request["method"] != "GET" or not path.startswith("data_sources/"):
            raise AssertionError("unexpected REST request: " + path)
        source = path.split("/")[1]
        return {"status": 200, "body": schema_body(source, sources[source])}

    return api


def rest_values(written):
    """Store REST write values, keyed by property ID, as REST page values."""
    return {
        key: {"id": key, "type": next(iter(value)), **copy.deepcopy(value)}
        for key, value in written.items()
    }


def field_for(kind, property_id):
    for field, spec in PROPERTIES[kind].items():
        if unquote(spec["id"]) == unquote(property_id):
            return field
    return None


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
        self.sources = {}
        self.add_page(PAGE)

    def add_source(self, data_source, kind, renamed=None, omit=()):
        self.sources[data_source] = (kind, renamed or {}, tuple(omit))

    def named(self, data_source, properties):
        """Key REST properties by current display name, as Notion responds."""
        kind, renamed, omit = self.sources[data_source]
        names = display_names(kind, renamed)
        result = {}
        for key, value in properties.items():
            field = field_for(kind, value.get("id", key))
            if field is None or field in omit:
                raise AssertionError(f"{kind} has no property {key}")
            spec = PROPERTIES[kind][field]
            result[names[field]] = {**copy.deepcopy(value), "id": spec["id"]}
        return result

    def add_page(self, page_id, title="Example", source=SOURCE, properties=None):
        """``properties`` holds REST values keyed by contract field."""
        self.sources.setdefault(source, ("chapters", {}, ()))
        kind = self.sources[source][0]
        values = {"title": {"type": "title", "title": [{"plain_text": title}]}}
        values |= properties or {}
        self.pages[page_id] = {
            "object": "page",
            "id": page_id,
            "parent": {"data_source_id": source},
            "last_edited_time": "0",
            "properties": self.named(
                source,
                {
                    field: {"id": PROPERTIES[kind][field]["id"], **value}
                    for field, value in values.items()
                },
            ),
        }
        self.children.setdefault(page_id, [])

    async def call_api(self, request):
        return await self(request)

    async def call(self, name, arguments):
        if name == "notion-create-pages":
            row = arguments["pages"][0]
            id = str(uuid.uuid4())
            source = arguments["parent"]["data_source_id"]
            kind, renamed, _ = self.sources.setdefault(source, ("chapters", {}, ()))
            title = row["properties"][display_names(kind, renamed)["title"]]
            self.add_page(id, title, source)
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
        elif method == "GET" and parts[0] == "data_sources":
            kind, renamed, omit = self.sources[parts[1]]
            body = schema_body(parts[1], kind, renamed, omit)
        elif method == "GET" and parts[0] == "blocks":
            body = {
                "object": "list",
                "results": [
                    self.nodes[id]
                    for id in self.children[parts[1]]
                    if not self.nodes[id].get("in_trash")
                ],
                "has_more": False,
                "next_cursor": None,
            }
        else:
            self.mutations += 1
            if method == "POST" and path == "pages":
                payload = request["json"]
                id = str(uuid.uuid4())
                source = payload["parent"]["data_source_id"]
                self.sources.setdefault(source, ("chapters", {}, ()))
                props = self.named(source, rest_values(payload["properties"]))
                self.pages[id] = {
                    "object": "page",
                    "id": id,
                    "parent": {"data_source_id": source},
                    "last_edited_time": "0",
                    "properties": props,
                }
                self.children[id] = [
                    self._create(node) for node in payload.get("children", [])
                ]
                body = self.pages[id]
            elif method == "PATCH" and path.endswith("/children"):
                ids = [self._create(node) for node in request["json"]["children"]]
                siblings = self.children[parts[1]]
                position = request["json"].get("position", {"type": "end"})
                if position["type"] == "start":
                    at = 0
                elif position["type"] == "after_block":
                    at = siblings.index(position["after_block"]["id"]) + 1
                else:
                    at = len(siblings)
                siblings[at:at] = ids
                body = {
                    "object": "list",
                    "results": [self.nodes[id] for id in ids],
                    "has_more": False,
                }
            elif method == "PATCH" and parts[0] == "pages":
                body = self.pages[parts[1]]
                source = body["parent"]["data_source_id"]
                properties = rest_values(request["json"]["properties"])
                body["properties"].update(self.named(source, properties))
            elif method == "PATCH" and parts[0] == "blocks":
                self.nodes[parts[1]].update(copy.deepcopy(request["json"]))
                body = self.nodes[parts[1]]
            elif method == "DELETE" and parts[0] == "blocks":
                self.nodes[parts[1]]["in_trash"] = True
                body = self.nodes[parts[1]]
            else:
                raise AssertionError(request)
            for page in self.pages.values():
                page["last_edited_time"] = str(self.mutations)
            if self.lose_reply == self.mutations:
                raise TimeoutError("response lost after mutation")
        return {"status": 200, "body": copy.deepcopy(body)}


async def write(reader, blocks, page_id=PAGE, *, targets=None, kind="chapters"):
    plan = await reader.prepare_content(page_id, blocks, targets=targets or {})
    plan = await reader.write_content(plan, checkpoint=lambda plan: None)
    return await reader.document(page_id, kind)


def roundtrip(blocks):
    async def run():
        api = BlockAPI()
        await write(NotionBooks(api=api), blocks)
        return (await NotionBooks(api=api).document(PAGE, "chapters")).blocks

    return asyncio.run(run())
