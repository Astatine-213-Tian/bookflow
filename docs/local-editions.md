# Local edition imports

Local EPUB/TXT files use the same prepared-book contract and Notion uploader as
web crawls. Use the installed commands below. Per-book decisions are reviewed
JSON data; reusable parsing, cleanup and upload logic belongs in `src/`.

## Prepare the supplied source

```bash
uv run book-prepare books/author/book.epub \
  --run-dir generated/book_import
```

Preparation copies the original, runs maintained Jinjiang metadata enrichment
and normalization/Codex review, and writes `source.json`, `prepared.epub`, cover assets, repair
reports and `normalization_diff.json` to the run directory. Review the complete
diff and unresolved findings before uploading. A second normalization pass must
be unchanged. Reusing the directory requires unchanged input bytes and options;
use a new directory for a new edition or a fresh metadata lookup.

EPUB navigation must account for every reading-order document. Unsupported
content or conflicting navigation stops preparation rather than dropping text.
The TXT adapter accepts UTF-8 or BOM-marked UTF-16 and explicit `第N章` headings,
plus standalone numbered `番外` headings. It preserves paragraph order and
repetition. Use `--title`/`--author` when TXT metadata headers are absent.

Jinjiang volume headings come from its structural directory report. Chapter
numbers and titles must align before assigning volumes. Edition title differences
produce `outline_review.json` and `chapter_aliases.proposed.json`. After checking
the source evidence, supply a JSON map of reviewed local-to-official titles:

```json
{"第9章 旧版标题": "官方标题"}
```

```bash
uv run book-prepare books/author/book.epub --run-dir generated/book_import \
  --chapter-aliases generated/book_import/chapter_aliases.proposed.json
```

Aliases validate identity; local chapter titles and bodies stay intact. Explicit
`--keep-outline` preserves an already reviewed local hierarchy. Author-defined
`番外卷` remains main text; standalone extras enter the shared extra library.

When a compiled edition numbers supplemental material as main chapters, supply
`--chapter-layout reviewed-layout.json` to `book-prepare` or `book-ingest` before
official-directory alignment. Each entry names an existing XHTML member, asserts
its normalized title, and explicitly partitions its blocks using zero-based,
half-open ranges. For example, split a six-paragraph afterword from an appended
extra without changing either body:

```json
{
  "EPUB/chap_01_171.xhtml": {
    "expected_title": "第171章 后记与补篇",
    "parts": [
      {"start": 0, "stop": 6, "role": "afterword", "title": "后记"},
      {"start": 6, "stop": 229, "role": "extra", "title": "补篇"}
    ]
  }
}
```

All blocks must be accounted for exactly once. Stale titles, gaps, overlaps and
unknown members fail before mutation. `chapter` retains main-text classification;
`afterword` stays in the main database outside numbered directory alignment;
`extra` enters the shared library in source order. Explicitly reviewed `omit`
parts require a `reason` and remain recorded in `layout_report`; the input edition
is always preserved. Classification is reviewed data, never inferred from the
absence of a chapter on the official site.

## Upload and verify

```bash
uv run book-notion upload --source generated/book_import/source.json \
  --cover-url https://example.org/public-cover.jpg
uv run book-notion verify --state generated/notion_cms_sources/HASH/import.json \
  --report generated/book_import/notion-verification.json
```

`upload` uses `notion-books` and the existing authenticated MCP transport for
book/chapter creation, duplicate checks, manual ordering and full content
readback. It reports progress and saves each returned page identity. New volume
options receive distinct colors from Notion's nine-color palette; existing
options retain their colors. More than nine volumes reuse the palette.

The prepared source records its embedded cover as a local asset with a byte hash;
loading the source verifies that hash. `--cover-url` overrides that asset,
validates a public PNG/JPEG and attaches it through MCP, then
verifies its URL and bytes. For an embedded/local cover, use `--cover path.jpg`
with `NOTION_API_TOKEN` (the prepared embedded asset is used by default); the
native upload path remains unchanged. Verification
reads every chapter and extra again, plus metadata, relations, order and recorded
presentation settings. Later editorial changes can legitimately differ from an
old import checkpoint; verification reports differences without overwriting them.

The unified entry point also accepts a local file or prepared JSON:

```bash
uv run book-ingest books/author/book.epub --mode notion \
  --run-dir generated/book_import --cover-url https://example.org/public-cover.jpg
uv run book-ingest generated/book_import/source.json --mode notion
```

Use the staged commands when the preparation reports need review. EPUB/TXT
outputs can also be selected through `book-ingest`; local input files are
preserved. Authentication and shared-extra reconciliation remain described in
[notion-books.md](notion-books.md) and [fanwai-notion.md](fanwai-notion.md).

## Recover a template through MCP

A created page ID does not prove asynchronous template application completed.
The importer waits for the owned chapter database and filtered extra view. If
that wait expires, inspect the existing work and checkpoint first. For a
confirmed empty work, use:

```bash
uv run book-notion recover-template --state generated/notion_cms_sources/HASH/import.json
uv run book-notion resume --state generated/notion_cms_sources/HASH/import.json
```

Recovery uses MCP `apply_template` on the existing work. It checkpoints the
request before sending it and never repeats an accepted or uncertain append.
Existing template content causes discovery only. A lost write response requires
readback/reconciliation, not another book creation. Normal imports and template
recovery do not require browser automation; initial OAuth login still opens its
authorization page.

## Compare editions only when requested

Version comparison is a separate, optional task for explicitly supplied files.
The standard preparation and import commands process one supplied source directly;
they neither search for alternative editions nor require a comparison report.

```bash
uv run book-compare books/author/book.epub research/datasets/raw/author/book.txt \
  --report generated/book_comparison.json
```

This read-only tool reports ordered paragraph differences, including intentional
repeated dialogue. It recommends the containing edition, or EPUB when the text
is identical; it does not prepare or import that edition. When both editions
have unique text, review the differences before choosing a source. A size
difference alone does not establish completeness. Comparison covers only the
supplied files.
