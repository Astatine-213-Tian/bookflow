# BookFlow

A personal book tool driven by coding agents. It finds sources, crawls sites or
imports EPUB/TXT/images, prepares the text, optionally translates it, and writes
EPUB, TXT or editable Notion drafts. Every path shares one
[book JSON](docs/content-json.md).

## Setup

Install `uv`, `mise` and `gh`, then follow the
[dependency setup](docs/notion-books.md#install-shared-dependencies): the private `notion-books`
package needs GitHub access and Go to build. Later syncs use
`mise exec -- uv sync --locked`. Browser-backed providers find Chromium
automatically; set `BOOKLIB_BROWSER_PATH` to choose one.

## Main commands

```bash
uv run book                       # list every subcommand
uv run book ingest --search "全球高考" --mode epub
uv run book ingest "https://www.mangguoshufang.com/1/2574/info.html" --mode epub --mode txt
uv run book prepare original.epub --run-dir generated/ingest/reviewed
uv run book notion upload --source generated/ingest/reviewed/source.json
uv run book update current.json --change change.json --run-dir generated/updates/run --mode epub
uv run book bilingual update eternal_gate --headless
uv run python -m unittest discover -s tests -p 'test_*.py'
```

Each command ends with one JSON result line. EPUB and TXT default to
`books/<author>/<title>.*`.

## Documentation

- [NORMALIZATION.md](NORMALIZATION.md): what normalization does to text, titles
  and structure, with examples.
- [AGENTS.md](AGENTS.md): agent instructions; book tasks use the
  [book-management skill](.agents/skills/book-management/SKILL.md).
- [Architecture](docs/architecture.md) and [local files](docs/storage.md).
- [Book JSON and changes](docs/content-json.md),
  [local editions](docs/local-editions.md),
  [Notion output and recovery](docs/notion-books.md),
  [shared extras](docs/fanwai-notion.md),
  [EPUB proofreading](docs/epub-proofreading.md),
  [Jinjiang proofreading](docs/jinjiang-proofread.md),
  [live Notion checks](tests/LIVE_NOTION.md).

Reader files, source text, browser profiles, credentials and working runs stay
out of Git. `research/` is a separate uv project for corpora and experiments.
