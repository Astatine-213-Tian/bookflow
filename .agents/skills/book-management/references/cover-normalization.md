# Cover normalization

Every library cover is **2:3** (width:height) and at most **1,000,000 bytes**.
Restore faithfully: keep the original cover and make it clearer, redesigning as
little as possible.

## When it runs

`book ingest` and `book notion upload` pass a new book's cover through
`src/workflows/cover.py` before any output and report its verdict under `cover`:

- `keep` (within 1% of 2:3, at least 800 px wide, no external white margin) and
  `crop` (within 5%; centered crop, never stretched) are delivered automatically.
- `restore` (anything else, including transparency or a cover that cannot fit the
  byte limit at JPEG quality 80) stops with `review_required` (`kind: cover`) and
  writes `cover-restoration.json`.

The verdict is mechanical: restore a delivered cover too when, at full size or as
a 120–160 px thumbnail, it is blurry or compression-damaged, or the crop touches
the title, credits or important art.

The stage is skipped for TXT-only runs, Notion-only runs given `--cover-url`, and
books without covers. Pass `--keep-original-cover` only for art books and
user-approved exceptions; a book about animation, film or art criticism is not an
art book. Existing library covers are reprocessed only when the user asks.

`book cover check FILE…` reports verdicts and reasons without writing;
`book cover normalize FILE -o OUT` writes the delivered `keep`/`crop` cover, and
with `--restored` checks a restored candidate is 2:3 and fits it to the limit.

## Restoring a cover

Work in the run directory beside `cover-restoration.json`, which names the
original (`cover-original.*`) and the source to rerun.

1. **References first.** Find a higher-resolution cover of the same edition,
   preferably from the publisher, the author or a reliable bookseller, and compare
   them before interpreting text or rebuilding detail. A clean same-edition scan
   that only needs cropping beats any regeneration.
2. **Geometry.** Show the front cover straight on at 2:3: remove spines,
   perspective distortion and external white margins, and adapt the composition
   without stretching. Keep intentional whitespace and user-approved ratio
   exceptions.
3. **Original design.** Keep the artwork, colors, composition, title lettering,
   credits and decorative details as close to the original as possible, and carry
   every accepted correction into later revisions.
4. **Every character verified.** Check titles, author and illustrator names, 著/绘,
   poems, introductions, promotional lines, punctuation and seals against reliable
   references. User-supplied wording wins; generated Chinese is never a source of
   truth.
5. **Typography.** Recover or reuse the original lettering where possible. Reset
   text matches its font character, weight, spacing, orientation, color and
   placement; related credits, especially 著 and 绘, share one style. Poems and
   introductions keep their visual character while becoming clearer.
6. **Authentic details.** Crop and reuse original seals, logos, calligraphy or
   text blocks when regeneration damages them. Every character on the cover comes
   from the original or verified wording, never invented text or decorative
   pseudo-text. Remove an unrecoverable optional detail cleanly; flag unresolved
   title or credit text to the user.
7. **Clarity and size.** Upscale when it meaningfully improves quality; restored
   covers are normally 1024 × 1536. Inspect small text at full size for broken
   strokes, halos and compression damage, then run
   `book cover normalize CANDIDATE -o OUT --restored`, preserving resolution
   where possible.

### Generating a candidate

Generate through Codex CLI's built-in `image_generation` tool (OpenAI GPT Image),
from Claude Code sessions too, passing the original and reference covers as input
images:

```bash
codex exec -C RUN_DIR -s workspace-write --skip-git-repo-check \
  -i cover-original.png -i reference.jpg \
  -o candidate-1.txt - < restore-prompt.md
```

`restore-prompt.md` gives the rules above, asks for a 2:3 front cover at
1024 × 1536 at an exact output file such as `candidate-1.png`, lists every title,
credit and line of text verbatim, and includes prior review comments for a
regeneration. The result is a draft that goes through steps 4–7 against the
original. Number each attempt's prompt and candidate anew so earlier candidates
stay comparable.

## Review

Show the user every changed cover from the round, and only those:

1. Write `manifest.json` beside the images:
   `{"round": "<book>-<date>", "items": [{"id", "title", "original", "proposed", "notes"}]}`,
   with the references used and any unresolved text in `notes`.
2. Run `book cover review manifest.json` and give the user `review.html`.
3. After the user clicks **Download decisions**, read
   `cover-decisions-<round>.json` (normally in `~/Downloads`). Only an `accept`
   whose `proposed_sha256` matches the file you will apply approves a cover; a
   built page or candidate never does. `regenerate` starts a new round with just
   those covers, carrying the comments forward; `keep_original` means rerun with
   `--keep-original-cover`.

## Applying the approved cover

- **New book:** repeat the original command with all its options plus
  `--cover APPROVED` (the exact approved file), reading the book from the
  `source` in `cover-restoration.json`: the saved `source.json` for a crawl, so
  the site is not crawled again, or the `--source` of `book notion upload`.
- **Existing library book,** only when the user asks: back up the current cover
  and EPUB, replace the cover with Bookshelf's `PUT /api/v1/books/{id}/cover`
  (which also updates the embedded EPUB cover), then verify that book content and
  reading progress are unchanged.

Keep the original, candidates, manifest and decisions in the run directory until
the book is complete; [storage](../../../../docs/storage.md) governs retention.
