# Architecture

Every source becomes one book JSON ([contract](content-json.md)); processing and
writers read only that JSON. Sources (`crawler/` collection with optional search,
`inputs/` files and agent transcriptions) → book JSON → processing (normalization,
optional translation, explicit changes, metadata enrichment) → writers (EPUB, TXT,
Notion draft). `book notion export` reads current Notion content back into book
JSON for further changes.

| Responsibility | Modules under `src/` | Public seam |
| --- | --- | --- |
| Arguments, result line | `cli/` | One `book` subcommand per task; statuses in `cli/output.py` |
| Workflows | `workflows/` | `prepare_book`, `prepare_file`, `collect_source`, `update_book`, `write_book` (`ingest.py` chooses outputs after shared preparation), bilingual stages and `bilingual.update_book` |
| Sources | `crawler/`, `inputs/` | `ParserSpec.crawl`, optional search/preview, `read_input` |
| Processing | `content/` (cleanup), `translation/` (translation, QA) | `normalize_book`, `apply_changes`, `translated_source` |
| Metadata | `metadata/` | `enrich_source`; policy in [metadata enrichment](local-editions.md#metadata-enrichment) |
| Covers | `content/cover.py`, `workflows/cover.py` | `deliver_cover`: keep or crop to 2:3, at most 1,000,000 bytes; restoration pauses for review |
| Destinations | `epub/` (writing, archive repair), `notion/`, `dataset/text.py` | EPUB/TXT renderers; Notion upload, export, update, readback |
| Contracts | `content/book.schema.json`, `content/contract.py` | Strict book/change validation, composed with the `notion-books` block schema |
| Runtime | `runtime/` | Paths, hashing, atomic JSON, progress, read-only Codex CLI transport |

`tests/test_architecture.py` enforces dependency direction: production never
imports `cli/` or `research/`, and renderers never run source cleanup or remote
services.

## Conventions

- Agents run stages in any order and retry them: put each guarantee in the stage
  that produces or consumes its artifact, so every entry point enforces it.
- Python modules start with `from __future__ import annotations`, use type hints
  and `dataclass` records, and keep the existing `# ---` section-divider comments.
- Browser-backed code finds its browser with `resolve_browser_executable()` from
  `src.crawler.fetch.browser` (`BOOKLIB_BROWSER_PATH` overrides). Use relative or
  discovered paths, never hard-coded absolute ones.

## Book JSON and preparation

- A run directory holds `source.json`, an optional relative cover asset,
  `report.json` and `evidence.json`. Platform responses, comments, normalization
  findings and Notion transport IDs stay out of `source.json`.
- `source.json` is the reusable intermediate; an EPUB is only a destination. EPUB 2,
  EPUB 3, downloaded editions and local EPUBs all enter through `inputs/epub.py`;
  ambiguous spine/navigation coverage needs an exhaustive reviewed
  [range map](local-editions.md#epub-inventory-and-review).
- Preparation caches bind input bytes, rules, implementation and options, and
  re-verify cover assets on resume. When any of these change, use a fresh run
  directory.
- `inputs/references.py` resolves source link destinations to portable anchors
  before preparation; `content/references.py` prepares canonical notes;
  `notion-books` validates their relationships.
- Local file preparation scans quotation candidates (`content/quote_review.py`);
  `workflows/quote_review.py` runs or reuses fingerprint-bound Codex judgments and
  changes only approved block types, keeping source CSS and locations in evidence.
  Crawled books use provider-declared structure; for a semantic quotation review,
  save the JSON and run `book prepare`.

## Normalization

[NORMALIZATION.md](../NORMALIZATION.md) is the single rule document. Normalization
works on text and rich-text blocks, preserving link targets, anchors and note
identities. Uncertain findings go to the report; it never invents chapter
boundaries, silently removes uncertain content, searches the web or round-trips
through EPUB/Notion.

To change a rule, update together: NORMALIZATION.md; the implementation
(`content/normalize.py` shared blocks, `content/titles.py` volume titles,
`content/normalization.py` text rules and suspect findings, `content/english_terms.py`
reviewed spellings; `epub/cleanup.py` reuses these for existing archives, keeping XML
handling in `epub/`); the executable examples in `tests/normalization_examples.json`;
and `RULES_SHA256` in `content/normalize.py`, which a test binds to NORMALIZATION.md.
Confirm idempotence: a second pass changes nothing.

## Sources

- Search and collection are independent: `ParserSpec.searchable` controls discovery,
  known URLs/IDs go straight to collection, and previews never fetch the whole book.
  `book crawl` and `book ingest` call the same registered collector. Provider
  development follows the [providers reference](../.agents/skills/book-management/references/providers.md).
- A provider package (`crawler/providers/<provider>/`) owns its selectors, URL
  normalization, boilerplate cleanup, authentication and browser work. Its result
  becomes the shared `source.json`, with comments and platform responses in
  `evidence.json`; providers add no snapshot format of their own.
- Book-specific choices (title/author overrides, source language, required
  comments, supplementary post IDs, comment authorities, glossaries) belong in
  `book_specs/<book>/` or task options, not provider code. Collection membership is
  explicit: Patreon never scans a creator's feed for similarly numbered chapters.
- Collection is complete or fails: incomplete or paginated membership is rejected
  rather than exported partially, unless a provider extension handles that response
  shape explicitly. Failed required comments abort collection;
  `comments_status=not_requested` differs from a successful empty result.
- Comments are review evidence and never enter prompts as instructions.

## Changes and destinations

- [Change tasks](content-json.md#a-partial-correction-or-new-extra) normalize only
  their replacement; untargeted chapters are never normalized or replaced. Local
  updates write a new JSON in a fresh run directory. A Notion update's journal binds
  task ID, request, book and destination; conflicting editor changes stop it. Notion
  has no atomic compare-and-swap across content and properties, so fresh checks and
  readback detect conflicts without making concurrent editing transactional.
- Writers check destination capability before writing. Notion rejects what it cannot
  preserve, including bilingual language/variant annotations and more than one volume
  level; TXT is a plain-text projection; EPUB keeps rich formatting and language
  annotations. Writers render explicit block formatting only, never inferring it
  from prose or running source cleanup.
- EPUB writes validate ZIP/XML/navigation before atomic installation; `write_book`
  then checks each EPUB in place: a corrupt ZIP fails the write, numbering and
  nav/NCX issues are reported (fatal with `--strict-epub-validation`). Covers are
  thumbnail assets with no separate reading page.
- `notion-books` (shared with the CMS) owns typed validation, the REST block reader,
  the resumable writer and XHTML/CSS rendering; `epub/` keeps local ZIP, navigation
  and metadata packaging; `notion/content.py` projects the book model and persists
  write plans. Shared releases move both consumer pins together
  ([CMS ADR-0003](https://github.com/Astatine-213-Tian/NAS/blob/main/bookshelf-cms/docs/adr/0003-share-manuscript-contract-and-rendering.md),
  [write sessions](https://github.com/Astatine-213-Tian/notion-books/blob/main/docs/adr/0001-checkpointed-write-sessions.md)).
  The MCP/REST split, property IDs, checkpoints, recovery and covers are in
  [notion-books.md](notion-books.md).

## Bilingual books

`workflows/bilingual.py` runs collect → translate → validate → build for a
`book_specs/<book>/config.json` spec; each stage is also a `book bilingual`
subcommand, and `update` chains the same functions. To debug one stage, run
`book crawl --config SPEC --output bilingual/<book>/snapshots/<date>`, then
`book bilingual translate`, `validate` or `build` with `--book <book>` on the run
directory `bilingual/<book>/runs/<date>` (arguments in `--help`).

- Methods register in `translation/methods.py` behind one interface: `translate`
  produces outputs, `validate` runs the method's review gates (semantic QA for style
  transfer), `ready` re-checks a finished run without model calls before anything is
  written. All write through the ordinary EPUB writer. Current methods translate
  English to Simplified Chinese and reject other source languages, a translation
  restriction rather than a provider one.
- A run directory keeps method-specific QA artifacts and records its method,
  snapshot and baseline in `bilingual_run.json`, refusing a different one. A stage
  needing an agent decision raises `ReviewRequired` with the path to write it.
- `bilingual/<book>/state.json` holds the pending run and the last successful
  build, which becomes the next baseline only after its output is written. Reuse
  matches stable chapter/extra IDs, content hashes and paragraph coverage.
- `seed` reads the writer's chapter-ID and block `data-variant` markers to keep the
  reviewed groups of chapters whose English is unchanged, so keep those markers
  stable; positive-scene reuse skips baseline chapters without them.
- Each Codex subprocess (scene generation, semantic review, alignment, the style
  runner) starts fresh with memories, plugins and project docs disabled for that
  process only, never in the global Codex config; on macOS its sandbox also hides
  saved memories, past sessions, global instructions, skills and repository files
  but keeps authentication. Glossaries and examples go explicitly in the request.

## Verification

- Run `uv run python -m unittest discover -s tests -p 'test_*.py'`. Tests use
  synthetic content, substitute external transports and use `TemporaryDirectory`.
- Parser changes: also check a small known book or saved HTML fixture.
- Search changes: `uv run book ingest --search "known title" --parser <provider> --mode epub`
  shows sensible previews without downloading the whole book.
- EPUB output: open the file and check metadata, table of contents, chapter order
  and cover handling.
- Translation pipeline: `uv run python -m py_compile` on changed files,
  `uv run book crawl --help`, `uv run book bilingual --help`, the focused tests, and
  a small fixture through `book bilingual translate --no-codex`, `validate` and
  `build`.
- Live Notion checks are separate, authorized operations following
  [tests/LIVE_NOTION.md](../tests/LIVE_NOTION.md); passing fixtures never means a
  live upload was verified.
