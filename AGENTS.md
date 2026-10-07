# Repository Guidelines

## Image Transcription

Transcribe supplied text images directly with Codex vision; never use traditional
OCR tools or services, including for drafts or fallback. For multiple images,
spawn parallel Codex agents with small batches and independently read every region
twice. Follow the [image transcription workflow](.agents/skills/book-management/references/image-transcription.md)
for long-image crops, coverage tracking and discrepancy resolution. Keep the raw
transcription, then apply the shared formatting rules before output and readback,
including quote direction and Chinese/Latin/digit spacing.

## Eternal Gate Updates

For “update eternal gate” / “更新永恒之门”, use this workflow:

1. Identify the latest successful crawl and translation run under `generated/`
   as the reuse baseline; preserve existing artifacts and glossary edits.
2. Run the maintained `uv run book-crawl --config book_specs/eternal_gate/config.json` command below with `--headless` and a
   fresh dated `--output` directory. The Patreon crawler manages its own browser
   and saved login profile; running it requires no browser skill setup.

   - **Recovery:** inspect an actual crawler failure before loading Agent Browser
     or BrowserAct. Use interactive browser tools only when the failure requires
     login, verification, or browser inspection, then resume the crawler. For the
     user's existing Arc session, use a verified `arc-cdp run <adapter>` adapter.
   - `src/cli/crawl.py` and `src/crawler/providers/patreon/parser.py` own the maintained
     crawling path.

3. Compare chapter bodies and fresh comments with the baseline. Reuse exact
   unchanged translation and style artifacts; translate and style only new or
   changed content using `book_specs/eternal_gate/config.json`. Review glossary
   changes against source evidence and preserve canonical names and protected
   quotations.
4. Run structural validation and semantic QA, then rebuild
   `books/顾雪柔/永恒之门.method4.bilingual.epub`. Verify chapter coverage,
   navigation, metadata, protected quotations, and placeholder scans before
   reporting completion. This update targets the bilingual EPUB; TXT export is
   a separate request.

## Project Structure & Module Organization

When changing module boundaries or adding an output destination, read
[docs/architecture.md](docs/architecture.md). Keep collection in `src/crawler/`,
source cleanup in `src/content/`, local EPUB writing/repair in `src/epub/`, Notion
upload in `src/notion/`, and translation/QA in `src/translation/`.
`src/inputs/` extracts files and provider content into the shared JSON;
`src/workflows/ingest.py` chooses outputs after shared preparation; `src/cli/` handles
arguments. Reusable logic belongs outside CLI modules. `tests/test_architecture.py`
checks dependency direction and the separation of cleanup from rendering.

For adding, updating or repairing books, use the single
[book-management skill](.agents/skills/book-management/SKILL.md). Ask for missing
output choices; EPUB, Notion draft and TXT can be combined. A training request
uses TXT plus the targeted dataset manifest. Notion storage and recovery follow
[docs/notion-books.md](docs/notion-books.md); shared extras follow
[docs/fanwai-notion.md](docs/fanwai-notion.md).
Render explicit formatting without matching prose. EPUB covers are thumbnail
assets with no separate reading page. Keep credentials and checkpoints local.

- `book_specs/` stores maintained per-book settings and reviewed glossaries.
- `assets/` stores reusable local inputs; `state/notion/` stores durable checkpoints.
- `generated/` stores working runs and retained translation baselines.
- `books/` stores final reader outputs grouped by author, not source code.
- `tests/` contains production contract tests.
- `research/` is an independent nested `uv` project for corpora and experiments;
  production must not import it. Dataset manifests live in `research/datasets/`.

For task artifacts and cleanup, follow [storage and retention](docs/storage.md).
Use system temporary directories for one-off scripts, probes, crops and previews;
tests use `TemporaryDirectory`. Keep a task's recovery and baseline data only as
specified there instead of archiving every intermediate under `generated/`.

## Build, Test, and Development Commands

For initial environment setup, follow
[dependency installation](docs/notion-books.md#安装共享依赖): the required private
`notion-books` package needs GitHub access and the pinned Go toolchain to build.
Use `mise exec -- uv sync --locked` for subsequent dependency syncs.

Run the unified entry point:

```bash
uv run book-ingest "https://www.mangguoshufang.com/1/2574/info.html" --mode epub -o books/book.epub
uv run book-ingest "http://jrkywsy.blog.fc2.com/blog-entry-938.html" --mode epub -o books/book.epub
uv run book-ingest 2574 --parser mgsf --mode epub -o books/book.epub
```

Run the search-and-preview pipeline:

```bash
uv run book-ingest --search "全球高考" --mode epub
uv run book-ingest --search "斗破苍穹" --parser quanben --mode epub
uv run book-ingest --search "全球高考" --first --mode epub -o books/book.epub
```

Use `uv run book-ingest --list-parsers` to inspect supported sites. Browser-backed providers such as xfxs and pili45 use `src.crawler.fetch.browser.resolve_browser_executable()` to find a Chromium-compatible browser. Set `BOOKLIB_BROWSER_PATH` to force a specific executable; otherwise discovery checks Playwright-managed Chromium, common executables on `PATH`, and common macOS app bundle paths.

Run the reusable crawl-then-translate stages as separate tasks. For Eternal Gate
updates, apply the reuse workflow above and use fresh dated crawl/run paths:

```bash
uv run book-crawl "https://www.patreon.com/collection/2218551?view=condensed" \
  --config book_specs/eternal_gate/config.json \
  --output generated/crawls/eternal_gate \
  --headless

uv run book-translate scene-positive generated/crawls/eternal_gate \
  --config book_specs/eternal_gate/config.json \
  --run-dir generated/translation_runs/eternal_gate_NEW \
  --baseline-snapshot generated/crawls/eternal_gate_BASELINE \
  --baseline-run generated/translation_runs/eternal_gate_BASELINE
uv run book-translate validate generated/translation_runs/eternal_gate_NEW \
  --config book_specs/eternal_gate/config.json
uv run book-translate build-epub generated/crawls/eternal_gate \
  --run-dir generated/translation_runs/eternal_gate_NEW \
  --config book_specs/eternal_gate/config.json \
  -o books/顾雪柔/永恒之门.method4.bilingual.epub
```

Dataset TXT output and manifests live under `research/datasets/`. The production
`book-ingest --dataset-root research/datasets` and `book-dataset` write there so crawling and
EPUB generation remain centralized while research owns the resulting corpus.
Run author-style experiments from `research/` with its own environment:

```bash
cd research
uv sync
uv run author-style-research verify
```

## Coding Style & Naming Conventions

Target modern Python 3 with `from __future__ import annotations`. Use 4-space indentation, type hints for data models and helpers, and `dataclass` for structured records. Keep constants in `UPPER_SNAKE_CASE`, classes in `PascalCase`, and functions or variables in `snake_case`. Prefer small parser/fetcher/build functions over large monolithic changes. Preserve the existing section-divider comment style for readability.

For new providers, create `src/crawler/providers/<provider>/parser.py` and, only when search is supported, `src/crawler/providers/<provider>/search.py`. Keep provider-specific selectors, URL normalization, boilerplate cleanup, and browser work inside the provider package. Register a collector in `src/crawler/registry.py` that accepts `CrawlOptions` and returns `CrawledBook`; keep output selection in `src/workflows/ingest.py` and ranking/selection in `src/crawler/search/orchestrator.py`.

Keep platform collection in `src/crawler/providers/<provider>/`. The workflow extracts its result to the shared `source.json`; keep comments/platform responses in `evidence.json`. Do not add another provider-specific snapshot format. Do not put book-specific translation choices in provider code; use `book_specs/<book_slug>/config.json` and `book_specs/<book_slug>/glossary.json`.

For browser-backed providers, do not hard-code Chrome or Chromium paths. Use `resolve_browser_executable()` from `src.crawler.fetch.browser`.

Provider `search.py` modules should expose:

```python
def search_books(query: str, *, limit: int = 10) -> list[SearchResult]: ...
def preview_book(result: SearchResult) -> BookPreview: ...
```

Prefer native site search. If unavailable, use `src.crawler.search.engines.site_search()` and filter results back to canonical provider book URLs. The shared helper uses no-key DuckDuckGo and raw Google result-page fallbacks. Preview should be lightweight: parse metadata and table-of-contents pages, but do not fetch all chapter bodies before the user chooses a result.

## Testing Guidelines

Keep documentation, dependency upgrades and verification scoped to this project.
Tests cover collection through the selected output: local EPUB/TXT or Notion
upload, readback and checkpoint resume. External publication and deployment are
outside this boundary. For live Notion upload checks, follow
[tests/LIVE_NOTION.md](tests/LIVE_NOTION.md).

Focused production contract tests live under `tests/` and run with
`uv run python -m unittest discover -s tests -p 'test_*.py'`. For parser
changes, also validate manually with a small known book or saved HTML fixture
when possible. For search changes, verify
`uv run book-ingest --search "known title" --parser <provider> --mode epub`
shows sensible previews without immediately
downloading the whole book. For EPUB output, open the generated file and confirm
metadata, table of contents, chapter order, and cover handling.

For translation-pipeline changes, at minimum run `uv run python -m py_compile ...`, `uv run book-crawl --help`, `uv run book-translate --help`, the focused production unit tests, and a small fixture through `book-translate prepare`, `validate --config`, `transfer-style`, and `build-epub`.

For generated bilingual EPUBs, the main Codex run retries failed chunks with narrower context and paragraph fallbacks. Empty `zh` values are allowed only after retry when a paragraph still cannot be translated and must produce no placeholder/refusal text. In that case validate the run with `book-translate validate --allow-missing --config ...`, then scan the final EPUB for placeholder strings and confirm only the intended paragraphs are English-only.

## Commit & Pull Request Guidelines

Use Conventional Commits for commit messages, such as `fix(xfxs): repair preview metadata` or `docs: update provider search notes`. Pull requests should describe the target site, commands used for validation, generated output path, and any manual steps such as Cloudflare verification.

## Security & Configuration Tips

Keep credentials, browser profiles, local book data and working runs out of Git.
Follow [storage and retention](docs/storage.md) for local paths and lifecycle.
Avoid hard-coded absolute paths.

## Agent skills

### Issue tracker

Use GitHub Issues for issues and specs. Read `docs/agents/issue-tracker.md`
before tracker operations.

### Triage labels

Use the five canonical triage labels. Read `docs/agents/triage-labels.md`
before applying or interpreting triage labels.

### Domain docs

Use a single-context layout. Read `docs/agents/domain.md` before exploring
domain concepts or architectural decisions.
