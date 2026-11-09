# Local input and preparation

Local EPUB, TXT, agent-built JSON and crawled `source.json` go through
`book prepare`, which never modifies its input. Record content selection in review
data; put reusable extraction fixes in `src/inputs/`.

```bash
uv run book prepare original.epub --run-dir generated/ingest/reviewed
uv run book ingest generated/ingest/reviewed/source.json --mode epub --mode notion \
  --run-dir generated/ingest/final -o books/AUTHOR/TITLE.epub
uv run book ingest original.txt --title TITLE --author AUTHOR --mode txt \
  --txt-output books/AUTHOR/TITLE.txt
```

Inspect the normalization findings in `report.json` before writing outputs.
`--chapter-layout` applies reviewed splits and main/extra/afterword roles per
chapter ID; each listed chapter's parts must cover all of its blocks (format:
`apply_edition_layout` in `src/content/edition_outline.py`).

Agent-built JSON follows the [content contract](content-json.md). When an
extractor cannot parse irregular TXT or images, read the source and supply that
JSON as a reviewed result; keep the difficult text.

Notion holds one parent level. For a 卷 → 回 → 章 source, map the volume (卷) to
`parent_title`, each 回 to a chapter row and its 题记 (epigraph)/章 labels to H3s
inside that row, rather than joining levels into the volume label. Confirm the reading units
with the source and user; combining units keeps every block in order.

## Metadata enrichment

`--enrich` replaces the selected fields with Jinjiang's values, falling back to
KadoKado only after a completed Jinjiang lookup finds no defensible match (never
after a network error); `volumes` applies the official volume titles. `volumes`
(and `all`) works on local inputs and on a prepared or crawled `source.json`;
`book ingest` given a URL, site id or `--search` accepts metadata fields only. To
give a crawled book its official volumes, prepare the crawl's `source.json` with
`--enrich all`, review, then ingest the reviewed `source.json`.

- `uv run book jjwxc TITLE --author AUTHOR` prints the official metadata and
  volume/chapter directory, read-only.
- Apply the official directory only after comparing every volume and chapter
  with this edition; title/author agreement does not prove its layout. `volumes`
  stops when a main `第N章` is missing from the directory, numbering is not
  continuous or a title differs; `--chapter-aliases` maps a reviewed local title
  to the official one without changing the body. Record lookup failures and
  edition differences.
- Explicit user values (including `--title`/`--author`) and an existing title,
  which may name a revised edition, are kept; an empty match never erases a value.
- A recorded Jinjiang source link identifies the work; otherwise exact title and
  author decide. Report ambiguous or locked matches instead of guessing.
- Conventions: the description is the 一句话简介 (one-line summary) without its
  label, never the full 文案 blurb (none → keep the existing one); subjects run `BL`, theme/genre, time-area
  (近代现代 → 近现代, 古色古香 → 历史背景); `〖…〗` series labels become the EPUB
  collection name and position.

For an existing archive, `book enrich-metadata FILE --check --report PATH`
proposes updates; unlike `--enrich`, it also writes the official title and
creator. It changes only the OPF: `dc:date` is the publication date,
`dcterms:modified` the edit time.

## EPUB inventory and review

Missing or contradictory coverage and body images need an explicit review
decision. Inventory first:

```bash
uv run book prepare original.epub --inventory --run-dir generated/ingest/inventory
```

`inventory.json` lists every spine page's blocks, anchors and TOC, plus the input
SHA-256. Write a review JSON with that hash and an entry for every listed page:

```json
{
  "sha256": "SHA256_OF_ORIGINAL_EPUB",
  "pages": {
    "Text/body.xhtml": [
      {"start": 0, "stop": 3, "role": "omit", "reason": "Reviewed copyright and 制作 pages"},
      {"start": 3, "stop": 7, "role": "intro", "title": "简介"},
      {"start": 7, "stop": 20, "role": "chapter", "title": "第一章", "parent": "正文·上（2008）"}
    ]
  }
}
```

- Ranges are zero-based, half-open and consecutive, and cover every block. Roles
  are `intro`, `chapter`, `afterword`, `extra` and `omit`; `omit` needs a
  `reason`. `parent` sets the volume title.
- Optional top-level `metadata` overrides are validated against the shared
  schema.
- A part's `replacements` entries (`index` absolute, exact `expected` block, new
  `block`) carry a reviewed image transcription or a confirmed extraction repair.
- Resolve number/title boundaries here: `卷一万物复苏` can parse as volume 10000.
  Once the source confirms volume 1, write `卷一 万物复苏`; normalization yields
  `卷一·万物复苏`.

```bash
uv run book prepare original.epub --review reviewed-ranges.json \
  --run-dir generated/ingest/prepared
```

Preparation rejects stale hashes, gaps, overlaps and unknown fields. An unchanged
rerun reuses its result; a changed source, rule or option needs a fresh run
directory. Local output cannot replace its input.

## Compare editions only when requested

```bash
uv run book compare first.epub second.txt --report /private/tmp/bookflow-edition-comparison.json
```

Comparison is not an import stage. It compares ordered chapter bodies and
meaningful repeats; keep uncertain unique material for review rather than
choosing an edition by size.

## Review possible quotations

EPUB extraction keeps source classes, CSS and paragraph locations in
`evidence.json`. A scanner selects unusual typography and explicit attributions
as candidates, and Codex classifies them: only a high-confidence `quote` changes
a paragraph's type, and other judgments keep text and formatting, with
uncertainty recorded in `quote-review.json`. A `.center` or small-font class alone
is not a quotation.

- `book prepare FILE --scan-quotes --review ranges.json --run-dir DIR` writes
  `quote-candidates.json` without calling a model. A session can then supply
  exact, fingerprint-bound decisions with `--quote-review decisions.json`.
- Otherwise preparation runs the locally authenticated `codex exec` (no API
  token), caches validated batches and resumes. Decisions may only classify:
  missing or duplicate IDs, rewrites and stale decisions are rejected.
- Use a fresh run directory when decisions change; the prepared cache binds them.
- `--quote-review` also works on `book ingest` for local files. For a crawl, save
  `source.json` first and run `book prepare` on it.

## Links and footnotes

EPUB links and declared footnotes are extracted before normalization. A unique
incoming note reference can repair a missing return anchor (recorded in the
evidence); other broken targets need review. In the review JSON, top-level
`link_overrides` maps an exact source href to `{"href": NEW_TARGET_OR_NULL,
"reason": ...}`; `null` keeps the visible text and drops only a proven-broken
link. When one occurrence is wrong, use a guarded block replacement rather than
retargeting every link to that URL.

## Existing EPUB maintenance

Visual proofreading, cover cleanup and filename/metadata cleanup follow
[EPUB proofreading](epub-proofreading.md); its reviewed per-book layout choices
override the defaults below.

`book normalize FILE --check` audits an existing archive; drop `--check` only for
an explicitly requested in-place repair. It enriches metadata (`--no-metadata`
skips), applies the [normalization rules](../NORMALIZATION.md) and supported XML
repairs, sends remaining findings to read-only Codex (`--no-codex-review` skips),
then validates. Block classification (numbered subheadings, lists, quotations)
happens only in `book prepare`.

### Reviewed structure

- Keep source- or user-confirmed volume boundaries and the complete chapter
  sequence. Standalone extras follow [shared extras](fanwai-notion.md). Classify
  extras from the source directory and body markers; content after `尾声`, `后记`
  or `全文完` is not automatically an extra.
- For an explicitly requested reorganization, unless the source or user says
  otherwise: prologue before the first main chapter, epilogue in the last main
  volume, afterword as a separate top-level chapter before a top-level extras
  group. A prologue is readable content, not intro metadata. A reviewed special
  parent such as `尾声·标题` can stay a volume-like group.
- After a confirmed volume marker moves into the directory, remove that exact body
  marker; keep prose that mentions the volume. Omit intro title/author lines only
  when confirmed as duplicate metadata.
- Merge multipart extras only at reviewed boundaries, never from a suffix alone:
  every part stays under a centered numbered H3 and later numbering is updated.
- A duplicate-number warning may mean a missing number; check the actual chapter
  identities before renaming. Preserve uncertain content.
- Everything the author wrote is content: chapter-end notes, comments, thanks,
  apologies, update notices, 收藏/投票 (bookmark/vote) pleas and mentions of their other books.
  Remove only advertising that sends readers to a third-party location (another
  website, account, group or download site). When unsure, keep it; list every
  removed line in full for review.

### Archive integrity and verification

- Prefer the maintained commands. A one-off structural patch belongs in
  `src/epub/`: parse XML, preserve inline formatting and attributes, and when
  reading order changes, update the XHTML titles/headings, `nav.xhtml`, `toc.ncx`
  and OPF manifest/spine together. Normalize confirmed volume labels with
  `normalize_volume_title` (`src/content/titles.py`).
- Back up to `/private/tmp/bookflow-codex-backups/`, keeping the path relative to
  `books/`, never beside reader outputs. Write a temporary archive, validate it,
  then replace atomically. `mimetype` stays first and uncompressed.
- Keep a reader-visible contents page in the spine as well as device navigation.
  EPUB 2 keeps the NCX and registers a new contents page in manifest, spine and
  guide. Automatic flat-NCX repair numbers bare main titles after a prologue only
  when every NCX entry, title and heading agrees; special sections stay
  unnumbered. Nested, mixed-numbered or inconsistent layouts need review.
- EPUB 3 writes `epub:type="toc"` with the literal `epub` prefix (Apple Books).
  Parent entries link to their first child. The cover is a thumbnail asset with
  no reading page. Visible chapter and prologue headings are centered.
- Run `uv run book validate-epub FILE`, then confirm a second pass changes
  nothing. Keep reports of fixes, review decisions and unresolved findings under
  `reports/normalization/`; inspect source defects before dismissing them.
