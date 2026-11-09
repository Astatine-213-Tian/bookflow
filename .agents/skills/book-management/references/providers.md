# Crawler Development

Providers only collect source material; `src/workflows/ingest.py` owns source
preparation and the selected outputs.

## Parser and Registry

- `src/crawler/providers/<site>/parser.py` exposes
  `crawl_book(url, ...) -> tuple[BookMeta, list[Volume]]`, reusing `Chapter` and
  `Volume` from `src.content.models` (a local `BookMeta` is fine when site
  metadata differs).
- Register a collector `run_<site>(target: str, options: CrawlOptions) -> CrawledBook`
  and its `ParserSpec` (`name`, `domains`, `description`, `crawl`) in
  `src/crawler/registry.py`, following an existing one. Import the provider inside
  the collector so discovery does not depend on any provider's dependencies.
- Inspect a saved HTML fixture first. Browser-backed collection stays inside the
  provider, following `xfxs`/`pili45`, and finds the browser with
  `src.crawler.fetch.browser.resolve_browser_executable()`. When a site rejects
  headless browsers, fail with a message to retry without `--headless`.

## Search and Preview

`search.py` exposes `search_books(query, *, limit=10) -> list[SearchResult]` and
`preview_book(result) -> BookPreview` (`src.crawler.search.models`). Search in
this order of preference:

1. Native site search page or endpoint.
2. Local provider index, if one exists.
3. `src.crawler.search.engines.site_search(query, site=..., path_prefix=..., limit=...)`
   (DuckDuckGo/Google), filtered back to canonical provider book URLs.
4. No search; keep `preview_book()` working for direct URLs if useful.

Where raw result pages throttle or block requests, optionally add
`search_books_with_browser(query, *, limit, browser)` with the same strategy
through Chromium.

Preview is a lightweight metadata layer: title, author, canonical book URL,
status when available, chapter count, first two and last two chapter titles and
a short intro, from the info and TOC pages through the parser's existing helpers.
Fetch chapter bodies only when the site has no table of contents. Return clean
candidates; ranking (query match, then chapter count, then provider priority)
belongs to `src/crawler/search/orchestrator.py`.

## Pagination and Completeness

- **TOC pagination:** follow `下一页`, numbered TOC pages or API offsets and crawl
  every TOC page before building `ChapterRef`s. Books over 100 chapters often hide
  later entries on `/2/<book_id>/2/`, `/3/`, …; the first page never proves
  completeness. Deduplicate by stable chapter id, not title: sites duplicate
  titles or split one into `(1)` and `(2)`.
- **Body pagination:** follow same-chapter next-page links such as
  `<chapter>_2.html`; stop at a link to another chapter id, a non-chapter URL, or
  no link.
- Preserve source order and let post-generation validation expose numbering
  problems instead of renumbering silently.
- For long books, test a subset spanning a TOC page boundary and a body
  pagination boundary.

## Concurrency

Correctness comes before speed.

- Honour `CrawlOptions.concurrency` with a conservative default and one rate
  limiter shared by all workers; multi-page chapters multiply requests and trigger
  `429`.
- Keep results in original `ChapterRef` order; log each completion with done,
  failed, remaining and the current chapter title.
- Retry failed chapters serially through the most reliable navigation path. If
  that also fails, raise: a book is written complete or not at all.
- Browser-backed: one browser with several tabs usually beats several processes,
  but initialize each worker tab on the site origin, or cookies/origin state can
  block it. If multi-tab setup times out, fall back to a shared tab or serial
  fetching instead of aborting. Several processes still share one IP rate limit;
  try pacing and fallback first.
- Browser `response.text()` can mis-decode legacy encodings: for GBK/Big5, fetch
  `arrayBuffer()`, return base64 to Python and decode the bytes explicitly.

## Source Cleanup

Site-specific boilerplate belongs in the provider; cleanup for every source
belongs in shared preparation (`src/content/`).

- End the intro at review headings such as `作品简评`, `编辑评价` or
  image-alt-prefixed `金.gif 作品简评`; keep intro metadata such as `内容标签`
  and `搜索关键字`.
- End FC2 post bodies at footers such as `FC2拍手标签从这里开始` and its
  Traditional variants.
- Remove embedded navigation, page-break prompts, duplicated chapter headings,
  site ads and empty paragraphs.
- Drop a chapter zero that mostly repeats the intro, comparing normalized
  paragraph overlap rather than raw strings.
- Convert Traditional Chinese sources with OpenCC `t2s` (title, author, intro,
  volume and chapter titles, paragraphs) after parsing, before preparation.

## Validation

```bash
uv run book ingest --list-parsers
uv run python -m compileall -q src
```

Then crawl a saved fixture or a small live book. Done when title and author are
correct; the intro has no reviews, editor comments or footers; chapter count and
first/last titles are plausible; TOC pages after the first and every part of a
paginated chapter are included; a concurrent run's requested refs, fetched
chapters, empty bodies and nav/TOC counts agree; Traditional sources come out
Simplified; and EPUB nav, TOC and spine reference no removed chapter.

A parser defect that also damaged an existing book is fixed in the parser first;
repair that book only when asked, following [formatting.md](formatting.md).
