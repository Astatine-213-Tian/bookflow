# EPUB Creator From Web

A personal book tool for finding sources, importing EPUB/TXT/images, preparing
content, translating chapters and writing EPUB, TXT or editable Notion drafts.
Every path uses the same [content JSON](docs/content-json.md). See the
[architecture](docs/architecture.md) for module ownership and the system diagram.

## Setup

Install `uv`, `mise` and `gh`, then follow the
[dependency setup](docs/notion-books.md#安装共享依赖). The pinned private
`notion-books` dependency requires GitHub access and Go at build time; subsequent
syncs use `mise exec -- uv sync --locked`. Credentials stay in private local state.
Content validation, REST manuscript access and XHTML rendering use the shared
`notion-books` contract. See [dependency setup](docs/notion-books.md#安装共享依赖).

Browser providers discover Chromium automatically. `BOOKLIB_BROWSER_PATH` can
select an executable. Patreon manages its own saved login profile; inspect an
actual crawl failure before opening an interactive browser for recovery.

## Find, acquire or import

```bash
uv run book-ingest --list-parsers
uv run book-ingest --search "全球高考" --mode epub
uv run book-ingest --search "全球高考" --parser mgsf --first --mode epub
uv run book-ingest "https://www.mangguoshufang.com/1/2574/info.html" --mode epub
uv run book-ingest 2574 --parser mgsf --mode epub --mode txt
uv run book-ingest original.epub --mode notion --run-dir generated/ingest/reviewed
uv run book-ingest original.txt --title 书名 --author 作者 --mode txt --txt-output books/作者/书名.txt
```

Search creates lightweight previews before collection. Known URLs skip search.
Downloaded EPUB editions use the same input adapter as local EPUBs and can go to
any supported destination. EPUB/TXT default to `books/<author>/<title>.*`.
Destinations must be explicit; `-o` or `--txt-output` can select a local format.

Preparation can be run separately for review and reuse:

```bash
uv run book-prepare original.epub --run-dir generated/ingest/reviewed
uv run book-prepare irregular.epub --inventory --run-dir generated/ingest/inventory
uv run book-prepare agent-content.json --run-dir generated/ingest/transcribed
```

See [local editions](docs/local-editions.md) for EPUB range review and comparison.
Images and irregular TXT can be parsed by an agent into schema-validated JSON;
use the [image transcription procedure](.agents/skills/book-management/references/image-transcription.md).
No traditional OCR is used. Normalization follows [one rule document](docs/normalization.md).
Metadata enrichment is optional (`--enrich-metadata`) and preserves explicit
values. Reports and cover assets stay beside prepared JSON under `generated/`.
Local preparation scans possible quotations and uses authenticated `codex exec`
only when candidates need judgment. Use `book-prepare --scan-quotes` to inspect
them first, or `--quote-review` for saved session decisions; see
[quotation review](docs/local-editions.md#review-possible-quotations).

## Update an existing book

```bash
uv run book-update current.json --change change.json --run-dir generated/updates/run \
  --mode epub -o books/作者/修订版.epub
uv run book-notion export --state generated/notion_cms_sources/RUN/import.json --report current.json
uv run book-notion update --state generated/notion_cms_sources/RUN/import.json --change change.json
```

[Change requests](docs/content-json.md#a-partial-correction-or-new-extra) identify
specific chapters and the content they were based on. Partial images become a
reviewed complete replacement chapter. Other content remains untouched. Notion
updates resume from journals and stop on conflicting editor changes.

## Notion

```bash
uv run book-notion login
uv run book-notion upload --source generated/ingest/reviewed/source.json
uv run book-notion resume --state generated/notion_cms_sources/RUN/import.json
uv run book-notion verify --state generated/notion_cms_sources/RUN/import.json
```

Official MCP preserves catalog metadata, linked views and manual chapter order.
Manuscript reads/writes use official REST and require `NOTION_API_TOKEN` with
access to the destination. Footnote binding uses REST block IDs; browser anchor
binding is removed. Covers require byte readback. Details: [storage/recovery](docs/notion-books.md),
[shared extras](docs/fanwai-notion.md) and the [reference contract](docs/content-json.md#hyperlinks-and-footnotes).
EPUB retains quotes, links and notes; TXT projects them to readable text.

## Collect and translate

```bash
uv run book-crawl --config book_specs/eternal_gate/config.json \
  --output generated/crawls/eternal_gate_NEW --headless
uv run book-translate --help
```

Collection saves the public `source.json` and separate comments/platform evidence.
Patreon collection membership is explicit; supplementary post IDs are book
configuration, never guessed from a creator feed. Other books can reuse the same
provider with different titles, authors and languages.

Translation currently targets English → Simplified Chinese. Neutral, author-style
and direct positive-scene methods retain their existing QA/reuse checks and all
write structured bilingual content through the ordinary EPUB writer. Follow the
book configuration and [Eternal Gate workflow](AGENTS.md#eternal-gate-updates).
Historical generated files are preserved, but new runs use the shared contract.

## Training and research

TXT output is independent of research. Request dataset bookkeeping explicitly:

```bash
uv run book-ingest "<url>" --mode txt --dataset-root research/datasets
uv run book-dataset export-txt --epub books/作者/书名.epub
uv run book-dataset upsert --txt research/datasets/raw/作者/书名.txt
```

Only the selected book's manifest entry is changed. Dataset classification can
use maintained metadata and the configured classifier. `research/` is an
independent nested uv project; production never imports experiments or corpora.

## Validation

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
uv run book-crawl --help
uv run book-translate --help
```

Tests use synthetic content and substitute external transports. Live Notion
validation requires the scoped workflow in [tests/LIVE_NOTION.md](tests/LIVE_NOTION.md).
Reader files, source text, browser profiles, credentials and generated runs stay
out of Git. Use the [book-management skill](.agents/skills/book-management/SKILL.md)
for operational book tasks.
