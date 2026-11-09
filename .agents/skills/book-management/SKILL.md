---
name: book-management
description: Add, find, update or repair books in bookflow. Use for choosing sources, crawling to local EPUB, Notion drafts and/or TXT, targeted training-dataset exports, transcribing book or extra text from images with Codex vision, adding or fixing crawler providers, and correcting or proofreading a book's formatting, structure, cover or metadata.
---

# Book Management

## Choose the Task

- **Add or reacquire a book from a site:** [Acquire a Book](#acquire-a-book).
- **Import a local EPUB/TXT edition:** [local editions](../../../docs/local-editions.md).
  Compare editions only when the user asks
  ([comparison](../../../docs/local-editions.md#compare-editions-only-when-requested)).
- **Transcribe supplied text images:** [image-transcription.md](references/image-transcription.md).
- **Source unsupported, incomplete or broken:** [providers.md](references/providers.md);
  then resume acquisition if a book output was requested. A provider-only task
  ends with its fixture and CLI checks.
- **Append images or correct part of a chapter:** [content JSON](../../../docs/content-json.md):
  transcribe into the shared schema, then apply an explicit change with
  `book update` or `book notion update`.
- **Check, crop or restore a cover** (including `review_required` with `kind: cover`):
  [cover-normalization.md](references/cover-normalization.md).
- **Upload or recover a Notion cover:** native API and byte readback in
  [notion-books.md](../../../docs/notion-books.md#cover); for a pending
  `cover-browser.json` or a requested browser upload, [notion-cover.md](references/notion-cover.md).
- **Correct an existing book's content, formatting, TOC or metadata:**
  [formatting.md](references/formatting.md).
- **Proofread an EPUB's typography, mixed-language punctuation, cover or download
  metadata:** [EPUB proofreading](../../../docs/epub-proofreading.md); apply only
  the previewed version the user confirms.
- **Proofread an existing edition against Jinjiang** (missing blank lines, suspect
  characters, author's notes): [Jinjiang proofreading](../../../docs/jinjiang-proofread.md);
  keep the selected edition and the destination the user names.
- **Export an existing book for training:** [Training Data](#training-data).
- **Bilingual book** such as Eternal Gate: “Bilingual Books” in `AGENTS.md`.

## Acquire a Book

1. **Choose destinations:** local EPUB, Notion draft, TXT, or a combination, from
   the request or established instructions. A supplied EPUB/TXT path or “add to
   the training dataset” already names one. Ask only about unresolved choices,
   researching the source meanwhile; add Notion or a training export only on
   request. Done when every destination is known.
2. **Find and verify the source.** `book ingest --search "<title>" --mode …`
   previews matches on supported sites without downloading them. For a Jinjiang
   work, `book jjwxc TITLE --author AUTHOR` (read-only) prints its page, metadata
   and official directory: volume titles, chapter numbers and titles, chapter
   count and 番外. It is the source for Jinjiang facts; compare every candidate's
   chapters against it. An unsupported or incomplete source goes to
   [providers.md](references/providers.md). Done when the chosen source is
   complete (against the official directory where one exists), or you have
   reported the gap.
3. **Write.** Crawl once; shared preparation normalizes wording, structure and
   formatting before any output.
   - **Direct:** `uv run book ingest "<url>" --mode epub --mode notion --mode txt`
     (any subset). On a URL, `--enrich` takes metadata fields only and never
     applies volumes.
   - **Reviewed structure** (e.g. applying the official volumes): crawl, prepare,
     review, then write from the reviewed source, with RUN under `generated/ingest/`.
     A changed input needs a fresh `--run-dir`.

     ```bash
     uv run book crawl "<url>" [--provider P] --output RUN/crawl
     uv run book prepare RUN/crawl/source.json --enrich all --run-dir RUN/reviewed
     # Review RUN/reviewed/report.json (normalization.issues) and the volume
     # sections in RUN/reviewed/source.json; apply reviewed edits to that file.
     uv run book ingest RUN/reviewed/source.json --mode … --run-dir RUN/final
     ```

   - **Extras:** only chapters marked `role: "extra"` (provider classification, a
     reviewed `--review`/`--chapter-layout` map, a TXT heading starting with 番外,
     or an `append_extra` change) go to Notion's
     [shared extras](../../../docs/fanwai-notion.md) database, after its duplicate
     check; EPUB keeps them under a trailing 番外 heading. Normalization gathers
     every other 番外-titled chapter not already under a 番外 heading into a
     trailing volume 「番外」 in the book. To keep extras in the book, mark none
     `role: "extra"`.
   - **Failure:** destinations run in sequence. Inspect the completed files and the
     Notion checkpoint, then resume that checkpoint
     ([Notion login and recovery](../../../docs/notion-books.md)) instead of
     recreating an uncertain Notion write. Use `--overwrite` only to replace
     outputs the request covers.

   Done when every selected destination is written.
4. **Verify and report.** EPUB: the check the write prints (ZIP, chapter
   numbering, nav/NCX), title, chapter order, and the delivered cover at full size
   and as a 120–160 px thumbnail, restored per
   [cover normalization](references/cover-normalization.md) if it fails. Notion:
   the upload's verified checkpoint. TXT: its content and, for a training export,
   its dataset manifest entry. Done when you have reported every actual path or
   Notion destination, with failures kept apart from completed outputs.

## Training Data

Training is a purpose of TXT output, not a separate crawler. For a new crawl add
`--mode txt --dataset-root research/datasets`, which also upserts the book in that
dataset's manifest. For an existing book, export its EPUB or upsert its TXT:

```bash
uv run book dataset export-txt --epub books/<author>/<title>.epub
uv run book dataset upsert --txt research/datasets/raw/<author>/<title>.txt
```

Use the dataset path the user names and pass their category overrides as
`--time-area`/`--genre`. Bulk export (`--books-root`) needs an explicitly
requested scope.
