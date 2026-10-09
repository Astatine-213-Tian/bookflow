# Content JSON and explicit changes

The executable contract is [`src/content/book.schema.json`](../src/content/book.schema.json).
`validate_book` rejects unsupported fields, unsafe identities, duplicate or
missing chapter references and invalid blocks before output. Book JSON is
version 3; change JSON is version 1 and reuses the schema's chapter definitions.

```json
{
  "version": 3,
  "identifier": "my-book",
  "metadata": {"title": "书名", "creator": "作者", "language": "zh-CN", "date": "2008-01-01", "subjects": ["danmei"]},
  "sections": [
    {"member": "intro"},
    {"id": "volume-one", "title": "正文·上（2008）", "children": [{"member": "chapter-1"}]}
  ],
  "chapters": {
    "intro": {"title": "简介", "role": "intro", "blocks": [{"kind": "paragraph", "runs": [{"text": "简介内容。", "styles": []}]}]},
    "chapter-1": {"title": "第一章", "role": "chapter", "blocks": [{"kind": "paragraph", "runs": [{"text": "正文。", "styles": []}]}]}
  },
  "extras": []
}
```

- `identifier` identifies the book; chapter dictionary keys and volume `id`
  identify content independently of its title. Assign stable `id` values to
  independent extras, especially before translation or updates.
- `sections` is an ordered tree of volume groups and chapter references. Each
  chapter appears exactly once. Maximum depth is three; Notion accepts one
  volume level. A volume named 番外 does not imply shared standalone extras.
- `role` is `intro`, `chapter`, `afterword` or `extra`. Independent extras live
  in `extras`; afterwords remain separate chapters in the outline.
- Block kinds are `paragraph`, `heading`, `quote`, `divider`. Runs support
  `bold`, `italic`, `underline`, `strikethrough`, `code`; explicit alignment is
  `left`, `center`, `right`, `justify`. New normalized subheadings use level 3.
  Bilingual blocks can declare `language` and `variant` (`original`/`translation`).
- Metadata supports title, creator/creators, language, date, source URL,
  description, subjects, series and series position. Unknown fields are errors.
  Year-only dates use January 1 during preparation. No explanatory note is added.
  EPUB retains all `creators`; TXT prints their names together. An explicit
  `--author` replaces the source author list. TXT is a reading projection;
  arbitrary volume/author labels require reviewed parsing when reimported.
- An optional `assets.cover` has `path`, `mime`, `sha256`. Paths are relative to
  the JSON directory and must remain inside it. Cover bytes are verified when
  loaded. Images in chapter bodies require transcription or an explicit
  reviewed omission; they are not silently passed to an unsupported destination.
- Keep original platform responses, page/image coverage, comments and metadata
  evidence in sibling evidence/review files. Do not put tokens, Notion page IDs,
  provider HTML or arbitrary attributes in content blocks.
- `related_works` contains content book identities, not destination page IDs.
  Notion rejects explicit values until there is a reviewed destination mapping;
  shared-extra duplicate review links existing pages while retaining their
  current work relations. It never silently treats these IDs as Notion pages.

For source selection, copyright/制作/阅读提示 removal and genre exclusions are
review decisions recorded in a task's EPUB range map or agent evidence. They are
not universal regex rules that delete paragraphs from every book.

## A partial correction or new extra

1. Read the current book JSON. For Notion use
   `book-notion export --state IMPORT --report current.json`; chapter text is
   freshly read, while book metadata/outline come from the import checkpoint.
2. Read supplied images using the image transcription workflow. Reconcile the
   affected region with current content and review a complete replacement
   chapter, preserving the rest. A new independent extra becomes one chapter.
3. Compute `content_hash(current["chapters"][chapter_id])` using
   `src.content.changes`. Save the explicit task below; do not hash transport
   checkpoint fields or a differently formatted string.
4. Run `book-update current.json --change change.json --run-dir generated/updates/run`
   for local content, or `book-notion update --state IMPORT --change change.json`.
   Repeat the same task ID to resume an interrupted Notion write.

```json
{
  "version": 1,
  "id": "chapter-1-correction",
  "book_id": "my-book",
  "operations": [
    {
      "kind": "replace_chapter",
      "chapter_id": "chapter-1",
      "expected_sha256": "SHA256_OF_CURRENT_CHAPTER",
      "chapter": {"title": "第一章", "role": "chapter", "blocks": [{"kind": "paragraph", "runs": [{"text": "完整修订章节。", "styles": []}]}]}
    }
  ]
}
```

Other operations:

| Kind | Fields besides `kind` | Meaning |
| --- | --- | --- |
| `append_chapter` | `chapter_id`, `after`, `chapter` | Insert after a stable chapter ID; `after: null` inserts at the start |
| `append_extra` | `chapter_id`, `chapter` | Add a standalone extra; the same ID/content is idempotent |
| `set_outline` | `expected_sha256`, `sections` | Replace only the complete reviewed outline; hash current `sections` |
| `metadata` | `expected_sha256`, `fields` | Set only supplied metadata; hash the current values of exactly those keys |

Missing fields do not mean deletion. Each chapter can be targeted once per task.
Unknown fields/operations or stale fingerprints fail before writing. Notion
currently accepts only the three chapter operations; metadata/outline changes
remain local JSON operations. Never reuse a completed task ID for new content.

## Hyperlinks and footnotes

A text run can add `href`; its displayed text and styles remain separate from
its destination. External HTTP(S)/mailto links retain their complete URL.
Portable internal links use `#anchor`. Blocks declare unique `anchor` values;
all internal targets must exist. A footnote block adds `footnote` with the same
ID, and reference runs use `link_role: "noteref"` or `"backlink"`.
Crawler links resolve against the chapter's source URL (book URL as fallback);
unambiguous collected destinations become internal anchors, while other web
links remain absolute URLs. Source IDs are namespaced per chapter.

Prepared footnotes use linked `[n]` in the body and `[n] note text ↩n` at the
chapter end. Multiple references get return labels `↩n.1`, `↩n.2`, in source
order. A multi-paragraph note is one note block with explicit paragraph breaks.
Footnotes belong to their referring chapter; unresolved cross-chapter notes are
rejected for review. Original unlinked editorial notes remain ordinary text.

The shared Notion REST block parser recovers this explicit paired structure from the document
itself. Platform block URLs are bound only by the Notion writer; an EPUB renders
local destinations, `epub:type="noteref"`, `epub:type="footnote"`, and return links.
TXT retains `[n]` plus endnotes and writes ordinary links as `text（URL）`.
URLs, anchor identities and note relationships are never text-normalized.

Block schema and semantic link validation belong to `notion-books`. The book
schema references its content schema ID; `content/contract.py` registers the
installed schema locally, with no network lookup.
