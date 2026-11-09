# Content JSON and explicit changes

The executable contract is [`src/content/book.schema.json`](../src/content/book.schema.json)
(book JSON version 3; change JSON version 1, reusing its chapter definition).
Block schema and semantic link validation belong to `notion-books`;
`src/content/contract.py` registers the installed content schema locally. Print
it with `uv run python -c "import json, notion_books; print(json.dumps(notion_books.CONTENT_SCHEMA, indent=1))"`.
`validate_book` rejects unknown fields, duplicate or missing chapter references
and invalid blocks before any output.

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

Conventions the schema does not express:

- `identifier` identifies the book; chapter keys and volume `id`s identify
  content independently of titles. Give independent extras stable `id`s,
  especially before translation or updates.
- `sections` references each chapter exactly once, at most three levels deep
  (Notion accepts one volume level). Independent extras (`role: "extra"`) live in
  `extras`, outside `sections`, and go to the shared-extras database; a volume
  titled 番外 stays book content ([shared extras](fanwai-notion.md)).
  Afterwords stay chapters in the outline.
- Year-only dates become January 1 during preparation, with no explanatory
  note. An explicit `--author` replaces the whole source author list. TXT is a
  reading projection; reimporting arbitrary volume/author labels needs reviewed
  parsing.
- `assets.cover` (`path`, `mime`, `sha256`) is relative to the JSON directory and
  must stay inside it; bytes are verified on load. Images in chapter bodies need
  transcription or an explicit reviewed omission before output.
- Keep platform responses, page/image coverage, comments and metadata evidence
  in sibling evidence/review files. Content blocks hold no tokens, Notion page
  IDs, provider HTML or arbitrary attributes.
- `related_works` holds content book identities, never destination page IDs.
  Notion rejects explicit values until a reviewed destination mapping exists;
  shared-extra duplicate review links existing pages and keeps their current
  work relations.
- Removing copyright/制作/阅读提示 text and genre exclusions are per-book review
  decisions recorded in the task's EPUB range map or agent evidence, not
  universal regex rules.

## A partial correction or new extra

1. Read the current book JSON. For Notion run
   `book notion export --state IMPORT --report current.json`: chapter text is
   read fresh, but metadata and outline come from the import checkpoint. Add
   `--chapter ID` per chapter for a targeted fix; only those are read, the rest
   keep their checkpoint copy.
2. Transcribe supplied images with the image transcription workflow. Reconcile
   the affected region with current content and review a complete replacement
   chapter, preserving the rest. A new independent extra is one chapter.
3. Compute `content_hash(current["chapters"][chapter_id])` with
   `src.content.changes` and save the change below. Hash the content JSON value,
   never checkpoint transport fields or a reformatted string.
4. Apply it with `book update current.json --change change.json --run-dir generated/updates/run`
   for local outputs, or `book notion update --state IMPORT --change change.json`.
   Rerun the same task ID to resume an interrupted Notion write; never reuse a
   completed task ID for new content.

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

`replace_chapter` merges the supplied fields over the current chapter, so
`blocks` must be the complete chapter; omitted fields are kept, not deleted.
Other operations:

| Kind | Fields besides `kind` | Meaning |
| --- | --- | --- |
| `append_chapter` | `chapter_id`, `after`, `chapter` | Insert after a stable chapter ID; `after: null` inserts at the start |
| `append_extra` | `chapter_id`, `chapter` | Add a standalone extra; the same ID and content is idempotent |
| `set_outline` | `expected_sha256`, `sections` | Replace the complete reviewed outline; hash current `sections` |
| `metadata` | `expected_sha256`, `fields` | Set only the supplied keys; hash the current values of exactly those keys |

Each chapter can be targeted once per task. Stale fingerprints fail before
writing. Notion accepts only the three chapter operations; outline and metadata
changes are local-only.

## Hyperlinks and footnotes

- A run adds `href`; its text and styles stay separate from the destination.
  External HTTP(S)/mailto links keep the complete URL. Internal links use
  `#anchor`; blocks declare unique `anchor` values and every internal target must
  exist. A footnote block adds `footnote` with the same ID; reference runs use
  `link_role: "noteref"` or `"backlink"`.
- Crawled links resolve against the chapter's source URL (book URL as fallback):
  unambiguous collected destinations become internal anchors, other links stay
  absolute. Source IDs are namespaced per chapter.
- Footnotes are linked `[n]` in the body and `[n] note text ↩n` at the chapter
  end; multiple references get `↩n.1`, `↩n.2` in source order. A multi-paragraph
  note is one note block with explicit paragraph breaks. Footnotes belong to
  their referring chapter; unresolved cross-chapter notes are rejected for
  review. Unlinked editorial notes stay ordinary text.
- EPUB renders local destinations, `epub:type="noteref"`/`"footnote"` and return
  links; TXT keeps `[n]` plus endnotes and writes links as `text（URL）`; Notion
  specifics are in [formatting conventions](notion-books.md#formatting-conventions). URLs, anchors and note
  relationships are never text-normalized.
