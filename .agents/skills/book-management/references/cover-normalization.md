# Cover normalization

Prefer faithful restoration: keep the original cover and make it clearer, with as
little redesign as possible. Every library cover is **2:3** (width:height) and at
most **1,000,000 bytes**.

## When it runs

`book ingest` and `book notion upload` pass a new book's cover through one stage
(`src/workflows/cover.py`) before writing any output:

| Verdict | Condition | Result |
| --- | --- | --- |
| `keep` | within 1% of 2:3, at least 800 px wide, no external white margin | Original pixels, re-encoded only to fit the byte limit |
| `crop` | within 5% of 2:3, otherwise as `keep` | Centered crop to exactly 2:3, never stretched |
| `restore` | anything else, including transparency or a cover that cannot fit the byte limit at JPEG quality 80 | Stops with `review_required` (`kind: cover`) and `cover-restoration.json` |

The result line reports the verdict under `cover`. The verdict is mechanical, so
look at the delivered cover at full size, and at a 120–160 px thumbnail, before
reporting the book complete. If it is blurry, compression-damaged, or a crop
touches the title, credits or important art, restore it anyway: follow the steps
below and rerun with `--cover`.

Covers are judged as readers display them (EXIF rotation applied) and converted
to RGB through their embedded color profile. TXT-only runs, and Notion-only runs
given `--cover-url`, skip the stage. Skip normalization with
`--keep-original-cover` for art books and approved exceptions. Books about animation, film or art criticism are not automatically
art books. Books without covers need nothing. Existing library covers are not
reprocessed unless the user asks.

`book cover check FILE…` reports verdicts and reasons without writing.
`book cover normalize FILE -o OUT` writes the delivered `keep`/`crop` cover;
`--restored` checks that a restored candidate is 2:3 and fits it to the limit.

## Restoring a cover

Work in the run directory beside `cover-restoration.json`, which names the
original (`cover-original.*`) and the source to rerun.

1. **Find better references first.** Search for a higher-resolution cover of the
   same edition, preferably from the publisher, the author or a reliable
   bookseller. Compare references before interpreting text or rebuilding detail.
   A clean same-edition scan that only needs cropping beats any regeneration.
2. **Geometry.** Show the front cover straight on at 2:3. Remove spines,
   perspective distortion and external white margins. Adapt the composition
   naturally without stretching; keep intentional whitespace in the design.
   Preserve ratio exceptions the user has approved.
3. **Original design.** Keep the artwork, colors, composition, title lettering,
   credits and decorative details as close to the original as possible. Carry
   every accepted correction into later revisions.
4. **Verify every character.** Check titles, author and illustrator names, 著/绘,
   poems, introductions, promotional lines, punctuation and seals against reliable
   references. User-supplied wording takes priority. Generated Chinese is never a
   source of truth.
5. **Preserve typography.** Recover or reuse the original lettering where
   possible. When text must be reset, match its font character, weight, spacing,
   orientation, color and placement; related credits, especially 著 and 绘, share
   one style. Poems and introductions keep their visual character while becoming
   clearer.
6. **Reuse difficult details.** Crop and reuse authentic seals, logos,
   calligraphy or text blocks when regeneration damages them. Never invent
   characters or decorative pseudo-text. Remove an optional detail cleanly when it
   cannot be recovered reliably; flag unresolved title or credit text to the user.
7. **Clarity and size.** Upscale when it meaningfully improves quality; restored
   covers are normally 1024 × 1536. Inspect small text at full size for broken
   strokes, halos and compression damage. Run `book cover normalize CANDIDATE -o
   OUT --restored` so the candidate is 2:3 and at most 1,000,000 bytes,
   preserving resolution where possible.

### Generating a candidate

Image generation runs through Codex CLI's built-in `image_generation` tool
(OpenAI GPT Image); Claude Code sessions call it the same way. Pass the original
and any reference covers as input images and give the rules above, the verified
wording, and an output path in the run directory:

```bash
codex exec -C RUN_DIR -s workspace-write --skip-git-repo-check \
  -i cover-original.png -i reference.jpg \
  -o candidate-1.txt - < restore-prompt.md
```

`restore-prompt.md` names the 2:3 front cover to produce at 1024 × 1536 and the
exact output file, such as `candidate-1.png`; lists every title, credit and line
of text verbatim; and includes prior review comments for a regeneration. Treat
the result as a draft: compare it with the original at full size, repair or reuse
damaged text and seals from the original (steps 4–6), then run
`book cover normalize … --restored`. Write a new prompt and candidate number for
each attempt, so earlier candidates stay comparable.

## Review

Show the user every changed cover from the round, and only those:

1. Write `manifest.json` beside the images:
   `{"round": "<book>-<date>", "items": [{"id", "title", "original", "proposed", "notes"}]}`.
   `notes` records the references used and any unresolved text.
2. Run `book cover review manifest.json` and give the user `review.html`. It shows
   original and proposal side by side with synchronized zoom and Accept, Keep
   original and Regenerate-with-comment controls.
3. The user clicks **Download decisions**; read the resulting
   `cover-decisions-<round>.json` (normally in `~/Downloads`). Only an `accept`
   whose `proposed_sha256` matches the file you will apply counts as approval.
   `regenerate` comments start a new round with just those covers; carry the
   comments forward. `keep_original` means rerun with `--keep-original-cover`.

Building the page or a candidate never authorizes using it.

## Applying the approved cover

- New book: repeat the original command with all of its options plus
  `--cover APPROVED`, using the exact approved file. Read the book from the
  `source` recorded in `cover-restoration.json`: for a crawl that is the saved
  `source.json`, so the site is not crawled again; for `book notion upload` it is
  the `--source`. EPUB and Notion outputs then carry that cover.
- Existing library book, only when the user asks: keep a backup of the current
  cover and EPUB, replace the cover with Bookshelf's `PUT /api/v1/books/{id}/cover`,
  which also updates the embedded EPUB cover, then verify that book content and
  reading progress are unchanged.

Keep the original, candidates, manifest and decisions in the run directory until
the book is complete; [storage and cleanup](../../../../docs/storage.md) governs
retention.
