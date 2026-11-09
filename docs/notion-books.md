# Outputs after crawling: EPUB, Notion draft and TXT

Choose outputs from the user's request; ask when none is given: local EPUB, a
[Notion draft](https://app.notion.com/p/3deca693996b810c8774f3658c89a423), TXT,
or any combination. Crawl once, then write each selected output; local-only
outputs never connect to Notion. Combined outputs run one at a time; after a
failure, check existing files and checkpoints and resume only unfinished outputs.
Notion output is done once the draft is written and verified by readback. Upload
never publishes; new chapters get content status 「未发布」.

## Install shared dependencies

Install `uv`, `mise` and the GitHub CLI (`gh`) first. `notion-books` is a
required private dependency, even for EPUB-only output, so the account needs
access to its GitHub repository. It is pinned to a version tag and `uv.lock`
records the exact commit; no sibling checkout is needed. First install, from the
repo root:

```bash
gh auth login
gh auth setup-git
mise trust
mise install
mise exec -- uv sync --locked
mise exec -- uv run --locked book notion --help
```

Help output from the last command means success; it does not connect to Notion.
On a Git permission error, confirm the `gh` account can access `notion-books`,
run `gh auth setup-git` and sync again. If the Go compiler is missing, run
`mise install` and sync through `mise exec --`.

Test local changes to the shared library with a temporary override, never by
editing the dependency config or lock file:

```bash
mise exec -- uv run --no-cache --with /absolute/path/to/notion-books python -m unittest discover -s tests -p 'test_*.py'
```

To upgrade, pick a published immutable tag, update both the version and the Git
tag, run `mise exec -- uv lock`, remove any local override and run the tests on
the locked version. The CMS also depends on `notion-books`; upgrade both sides
together.

## Usage

```bash
uv run book notion login
uv run book notion upload --source generated/ingest/reviewed/source.json
uv run book ingest "BOOK_URL" --mode epub --mode notion --mode txt
# Optional independent audit; upload already verifies every page by readback
uv run book notion verify --state state/notion/HASH/import.json
```

`book notion upload` takes the reviewed shared `source.json`; write no upload
scripts.

- **Auth**: official MCP (OAuth, `book notion login`/`logout`) handles catalogs,
  templates, linked views and manual order; official REST (`NOTION_API_TOKEN`
  from the environment or the repo `.env`) handles pages, properties, authors,
  covers and bodies. The REST integration needs access to the target databases
  with read, insert and update content permissions. Credentials never go into
  checkpoints.
- **Write order**: pages are created one by one in reverse to keep manual order.
  A body that fits in a single create is written with it; other bodies are
  written only after every page exists, because a block append right after a
  create that carries a body can be lost. When chapters are link targets, all
  pages are created before any body is written.
- **Verification**: upload checks each body, reads back properties and finally
  checks TOC order, so no full `verify` is needed afterwards. Use `verify` for
  independent audits and recovery investigations.
- **Concurrency**: parallel agents may decode, clean, structure-check and review
  edition hints for several books locally; only one Notion write process runs at
  a time. A second one fails with `Another Notion sync command is running`;
  retry after the first finishes.
- **During writes**: ask the user not to edit chapters being written; edits to
  old blocks during cleanup may be archived and can be restored from Notion
  history.

### Cover

Covers use the official File Upload API. Before upload, the cover is normalized
to 2:3 and at most 1,000,000 bytes per
[cover normalization](../.agents/skills/book-management/references/cover-normalization.md);
when it needs repair, upload pauses, and after approval you rerun with
`--cover`. `--keep-original-cover` (art books or approved exceptions) skips
normalization but still has the PNG/JPEG limit of 10 MiB and 25 million pixels.

For an existing `cover-browser.json` task, follow the
[cover procedure](../.agents/skills/book-management/references/notion-cover.md),
then run `book notion verify-cover --state ...` to read the bytes back over REST.
Cover recovery is separate from bodies: an unreadable cover or mismatched
readback stays pending and never causes bodies to be rebuilt.

## Notion storage

- Catalog IDs live in `book_specs/notion/config.json`. New books and authors are
  created from the works and authors databases' default templates, read by page
  ID; templates may be renamed, and switching templates only means setting
  another default in Notion. A database without a default template fails before
  any write.
- Each book gets its own chapter database from the template, identified by its
  book page and property IDs, never by name. Page title = chapter title;
  `parent_title` is optional. TOC order comes from the unfiltered, ungrouped,
  unsorted manual view; the 「待发布」 view does not define the TOC.
- Notion supports chapters plus one parent-title level; equal parent titles group
  only when consecutive. Deeper TOCs fail before upload; use local EPUB for them.
- Intro, epilogue, afterword and chapters inside a 番外卷 are all chapter rows;
  intro metadata is stored separately from the readable intro chapter. Only
  standalone extras with `role: "extra"` go to the shared database; see
  [shared extras](fanwai-notion.md).
- Properties are identified by Notion property ID: `notion-books` `PROPERTIES`
  defines each database's (`works`, `authors`, `extras`, `chapters`) contract
  fields, property IDs and types, and code reads and writes by field name, never
  by column header. Headers may be renamed freely in Notion; deleting a template
  property or changing its type fails before writing.
- Works receive only contract content properties (`title`, `authors`,
  `subjects`, `series`, `series_position`, `language`, `description`, `source`,
  `publication_date`). Upload adds only missing select options and keeps other
  properties, buttons and existing options.
- A source may supply several authors; never split pen names yourself. Existing
  authors are reused. A new author's homepage comes from a Jinjiang author search
  with exactly one match, written as `homepage` in the same create and read back.
  A failed search aborts the create; only an explicit no-match leaves it empty.
  An authors database without that property fails before the create when a
  homepage is found.

## Resume and conflicts

The checkpoint is `state/notion/<source-digest>/import.json`, isolated by target
catalog and source; never reuse it across target databases. It records every ID
a create returns and marks items verified after readback. After upload, Notion
edits are authoritative: edit uploaded content in Notion, and rebuild a local
copy with `--mode epub`.

```bash
uv run book notion resume --state state/notion/<source-digest>/import.json
```

- Uncertain create result: match the ID by page content and repair the
  checkpoint; never recreate. After an interrupted body write, `resume` checks
  the remote state from the last saved plan and never re-appends.
- A book with the same title exists: check book identity and the original
  checkpoint; never overwrite an existing book.
- A new crawl differs from the checkpoint: compare the local source with Notion
  edits and agree on a merge before continuing.
- Suspected duplicate extra: upload pauses and writes `extra-review.md` next to
  the checkpoint; resolve it per
  [shared extras](fanwai-notion.md#resolve-suspected-duplicates), then resume.
- Actual order differs: reorder the manual view to source order, then resume;
  never add a numeric sort column.
- `cover_pending` (uncertain cover attachment): run
  `book notion verify-cover --state ...` to check the current native image bytes;
  never set `cover_uploaded` to true by hand.
- Template content missing: it can appear late after Notion reports success, so
  upload waits up to about ten minutes; a blank page does not mean failure. After
  a timeout, `resume` the same checkpoint or run
  `book notion recover-template --state ...`, which only waits for the original
  request's result. Never reapply the template or copy databases by hand; the
  late request would then create duplicate databases.

## Formatting conventions

`src/content/` owns cleanup and format detection; the shared `notion-books`
dependency owns the content contract, Notion schema, REST property and body
reads/writes, and XHTML/CSS rendering; `src/notion/cms.py` and `upload.py` own
import decisions, identity matching, checkpoints and flow, with auth and cover
HTTP clients also in this project. Module boundaries:
[architecture](architecture.md). Supported scope: the
[notion-books content contract](https://github.com/Astatine-213-Tian/notion-books#content-contract).

- Chapters and extras share one block and rendering model; formatting comes only
  from explicit attributes. Cleanup rules are in
  [NORMALIZATION.md](../NORMALIZATION.md); writers never infer formatting from
  prose or redo cleanup.
- Alignment: Notion marks center or right alignment with the single non-empty
  column of a three-column row, not arbitrary multi-column layout. A chapter
  epigraph is a quote block whose attribution is a right-aligned child paragraph,
  i.e. a three-column row inside the quote (see
  [NORMALIZATION.md](../NORMALIZATION.md#链接脚注与引用块)).
- Footnotes and the paragraphs that reference them must be top-level. Paired
  footnote format: [content-json.md](content-json.md#hyperlinks-and-footnotes).
  The shared codec recovers footnotes, anchors and local links from Notion
  without the checkpoint; native quote blocks become EPUB blockquotes.
- Internal links: links to chapters of the same book and related standalone
  extras are written as Notion page URLs and restored to local links on export;
  content identity never includes Notion page IDs. Ordinary internal links may
  target only a chapter's start; arbitrary paragraph anchors (same chapter too)
  are rejected before writing, never downgraded to the chapter start. Paired
  footnotes and backlinks are exempt.
- Inline code cannot contain newlines, a literal `<br>`, backticks or a trailing
  backslash; MCP cannot preserve them unambiguously.
- Lists: flat numbered items are paragraphs with a literal `1. `, `2. ` prefix;
  native bulleted and numbered lists (including mixed nesting) are read and
  written by the shared SDK; other unsupported blocks fail on read.
- Notion rejects features it cannot map yet, e.g. block-level bilingual notes,
  justified text and H4–H6; local EPUB keeps them, with no silent downgrade.

Preview headings, quotes, links and footnotes with the production renderer:

```bash
mise exec -- uv run --locked notion-books preview --output /private/tmp/bookflow-format-preview
open /private/tmp/bookflow-format-preview/index.html
```

### End-of-chapter author notes

Put a top-level divider at the chapter end, followed by a plain paragraph that
starts with `作者有话说` or `作者有话要说` (colon optional, note text may follow on
the same paragraph, empty paragraphs after the divider allowed). From the label
to the chapter end, EPUB paragraphs keep body font size without first-line
indent; list levels, bold and explicit alignment are unchanged. Story text
belongs before the divider; small labels inside the note such as `超阶法宝：` stay
plain paragraphs, not H2/H3. The same words in quotes, lists or body text do not
trigger it. The shared renderer owns this rule and upload never rewrites text;
[normalization](../NORMALIZATION.md) inserts the divider before a non-empty
author note that follows body text.
