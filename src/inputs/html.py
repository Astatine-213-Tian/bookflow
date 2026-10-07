"""Read XHTML into explicit blocks before reviewed edition preparation."""

from __future__ import annotations

import html
import posixpath
import re

import cssselect2
import tinycss2

from src.inputs.references import EPUB_TYPE, is_footnote, source_anchor, source_href
from lxml import etree as ET


def declarations(tokens) -> dict[str, str]:
    return {
        item.lower_name: tinycss2.serialize(item.value).strip()
        for item in tinycss2.parse_declaration_list(
            tokens, skip_comments=True, skip_whitespace=True
        )
        if item.type == "declaration"
    }


def parse_xml(data: bytes) -> ET._Element:
    declaration = re.match(rb'<\?xml[^>]*encoding=[\'"]([^\'"]+)', data)
    encoding = (
        "utf-16"
        if data.startswith((b"\xff\xfe", b"\xfe\xff"))
        else declaration[1].decode("ascii")
        if declaration
        else "utf-8-sig"
    )
    text = data.decode(encoding)
    text = re.sub(r"^<\?xml[^>]*\?>", "", text)
    # EPUB 2 XHTML commonly relies on the external XHTML DTD for named entities.
    # Expand only known HTML entities; never fetch a DTD or recover malformed XML.
    text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;)([A-Za-z][A-Za-z0-9]+);",
        lambda match: html.unescape(match[0]),
        text,
    )
    return ET.fromstring(
        text.encode(), ET.XMLParser(resolve_entities=False, no_network=True)
    )


def read_html_blocks(
    data: bytes,
    member: str,
    files: dict[str, bytes],
    *,
    anchors: dict[str, int] | None = None,
    evidence: dict[int, dict] | None = None,
    base_url: str | None = None,
) -> list[dict]:
    root = parse_xml(data)
    styles = [n.text or "" for n in root.findall(".//{*}style")]
    for link in root.findall(".//{*}link[@rel='stylesheet']"):
        name = posixpath.normpath(
            posixpath.join(posixpath.dirname(member), link.get("href"))
        )
        styles.append(files[name].decode("utf-8-sig"))
    matcher = cssselect2.Matcher()
    for rule in tinycss2.parse_stylesheet(
        "\n".join(styles), skip_comments=True, skip_whitespace=True
    ):
        if rule.type == "qualified-rule":
            for selector in cssselect2.compile_selector_list(rule.prelude):
                matcher.add_selector(selector, declarations(rule.content))
    computed = {}
    inherited = {
        "text-align",
        "font-weight",
        "font-style",
        "text-decoration",
        "font-size",
        "font-family",
        "color",
    }
    for wrapper in cssselect2.ElementWrapper.from_xml_root(root).iter_subtree():
        node = wrapper.etree_element
        parent_style = computed.get(node.getparent(), {})
        values = {key: value for key, value in parent_style.items() if key in inherited}
        for _, _, pseudo, payload in matcher.match(wrapper):
            if pseudo is None:
                values.update(payload)
        values.update(declarations(node.get("style", "")))
        computed[node] = values
    blocks = []
    found_anchors = anchors if anchors is not None else {}

    def tag(node):
        return ET.QName(node).localname if isinstance(node.tag, str) else ""

    def runs(node, active=(), link=None):
        if node.get("id"):
            found_anchors[node.get("id")] = len(blocks)
        if node.get("href"):
            link = {"href": source_href(member, node.get("href"), base_url=base_url)}
            if (
                "noteref" in node.get(EPUB_TYPE, "").split()
                or node.get("role") == "doc-noteref"
            ):
                link["link_role"] = "noteref"
            elif node.get("role") == "doc-backlink":
                link["link_role"] = "backlink"
        result = []
        styles = list(active)
        local = tag(node)
        values = computed[node]
        for enabled, style in [
            (local == "code", "code"),
            (
                local in {"b", "strong"}
                or values.get("font-weight") in {"bold", "700", "800", "900"},
                "bold",
            ),
            (
                local in {"i", "em", "cite"} or values.get("font-style") == "italic",
                "italic",
            ),
            (
                local == "u" or "underline" in values.get("text-decoration", ""),
                "underline",
            ),
            (
                local in {"s", "del"}
                or "line-through" in values.get("text-decoration", ""),
                "strikethrough",
            ),
        ]:
            if enabled and style not in styles:
                styles.append(style)

        def add(text):
            if text:
                result.append({"text": text, "styles": styles.copy(), **(link or {})})

        add(node.text)
        for child in node:
            local = tag(child)
            if not local:
                pass
            elif local == "br":
                add("\n")
            elif local in {"img", "image"}:
                raise ValueError(
                    f"Mixed inline image requires explicit review: {member}"
                )
            elif local in {
                "span",
                "a",
                "b",
                "strong",
                "i",
                "em",
                "u",
                "s",
                "del",
                "code",
                "cite",
                "sup",
                "sub",
            }:
                result.extend(runs(child, styles, link))
            else:
                raise ValueError(f"Unsupported inline element {local}: {member}")
            add(child.tail)
        return result

    def visit(node, *, quoted: bool = False):
        local = tag(node)
        if node.get("id"):
            found_anchors[node.get("id")] = len(blocks)
        if not local:
            return
        images = [n for n in node.iter() if tag(n) in {"img", "image"}]
        if (
            images
            and not "".join(node.itertext()).strip()
            and local not in {"body", "div"}
        ):
            for image in images:
                href = image.get("src") or image.get(
                    "{http://www.w3.org/1999/xlink}href"
                )
                blocks.append(
                    {
                        "kind": "image",
                        "asset": posixpath.normpath(
                            posixpath.join(posixpath.dirname(member), href)
                        ),
                        "runs": [],
                    }
                )
            return
        if local == "br":
            blocks.append({"kind": "paragraph", "runs": []})
            return
        quoted = quoted or local == "blockquote"
        if local in {"body", "div", "ul", "ol", "table", "tbody", "tr", "section"} or (
            local in {"td", "li", "blockquote", "aside"}
            and any(tag(child) in {"p", "div", "ul", "ol", "table"} for child in node)
        ):
            if (node.text or "").strip():
                blocks.append(
                    {
                        "kind": "quote" if quoted else "paragraph",
                        "runs": [{"text": node.text, "styles": []}],
                    }
                )
            for child in node:
                visit(child, quoted=quoted)
                if (child.tail or "").strip():
                    blocks.append(
                        {
                            "kind": "quote" if quoted else "paragraph",
                            "runs": [{"text": child.tail, "styles": []}],
                        }
                    )
            return
        if local not in {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "aside",
            "hr",
            "li",
            "td",
            "a",
            "span",
        }:
            raise ValueError(f"Unsupported block {local}: {member}")
        block = {
            "kind": "heading"
            if re.fullmatch(r"h[1-6]", local)
            else {"blockquote": "quote", "hr": "divider"}.get(local, "paragraph"),
            "runs": runs(node),
        }
        if quoted and block["kind"] == "paragraph":
            block["kind"] = "quote"
        if block["kind"] == "heading":
            block["level"] = 3
        if computed[node].get("text-align") in {"center", "right", "justify"}:
            block["alignment"] = computed[node]["text-align"]
        if node.get("{http://www.w3.org/XML/1998/namespace}lang"):
            block["language"] = node.get("{http://www.w3.org/XML/1998/namespace}lang")
        if node.get("data-variant"):
            block["variant"] = node.get("data-variant")
        if node.get("data-book-anchor"):
            block["anchor"] = node.get("data-book-anchor")
        if node.get("data-book-footnote"):
            block["footnote"] = node.get("data-book-footnote")
        note = next((n for n in [node, *node.iterancestors()] if is_footnote(n)), None)
        if note is not None:
            note_id = note.get("id")
            if not note_id:
                raise ValueError(f"Footnote lacks an anchor: {member}")
            block["footnote"] = note.get("data-book-footnote") or source_anchor(
                member, note_id
            )
        if evidence is not None:
            evidence[len(blocks)] = {
                "member": member,
                "block_index": len(blocks),
                "tag": local,
                "classes": node.get("class", "").split(),
                "style": computed[node],
            }
        blocks.append(block)

    body = root.find("{*}body")
    if body is None:
        raise ValueError(f"document lacks body: {member}")
    visit(body)
    for name, index in found_anchors.items():
        if index < len(blocks):
            blocks[index].setdefault("anchor", source_anchor(member, name))
    for index, block in enumerate(blocks):
        if anchors is not None and block["kind"] != "image":
            block.setdefault("anchor", source_anchor(member, f"__block_{index}"))
    return blocks
