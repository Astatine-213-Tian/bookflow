# Shared extras

Only chapters explicitly marked `role: "extra"` go to the shared-extras database
(`databases.extras`; displayed as 「共享番外」): provider classification, a
reviewed EPUB range map (or the EPUB's own `data-book-role`), TXT headings
starting with 番外, or an `append_extra` change. They live in the content JSON's
`extras`, and only they get the duplicate check (`src/notion/duplicates.py`).

Every other 番外 chapter stays in the book. A 番外卷 defined by the author or
confirmed by the user keeps its source title, order and continuous chapter
numbering; chapters titled with 番外 outside any 番外 heading are moved by
normalization, in order, into a trailing 「番外」 volume (merged into an existing
trailing 番外 volume). A volume named 番外 does not make its chapters shared
extras. Before migrating an extra into the shared database, check the full
text so the same content is not stored twice.

The shared database lives in the
[Notion library](https://app.notion.com/p/3deca693996b810c8774f3658c89a423) and
links each extra to one or more books via `related_works` (displayed as
「涉及作品」). Each book's extras view filters to that book with its own manual
order. Upload, auth, recovery and formatting: [Notion output](notion-books.md).

## Duplicate check

The check runs only before a Notion upload; local EPUB/TXT-only output never
connects to Notion and skips it.

- MCP reads the shared database's complete inventory and versions; REST reads
  new or changed bodies. It never relies on title or keyword search, so renamed
  extras are still caught. An incomplete check, a filtered shared view or a
  failed body read aborts the upload; a missed read never counts as "no
  duplicate".
- Comparison ignores whitespace, punctuation, traditional/simplified script,
  case and formatting. Any of these flags a candidate: identical normalized
  text; local overlap (shared runs of at least 20 characters covering at least
  60 in total, regardless of overall share); overall similarity (both at least
  80 characters, 4-gram overlap at least 70%); partial containment (shorter
  version at least 80 characters, containment at least 60%, for proofread,
  incomplete, completed or anthology versions).
- The check errs toward flagging; similarity is a review hint, not a judgment of
  which version is better. It is not semantic: rewritten text without long
  enough shared runs can still slip through.
- A single candidate with identical title and formatted body is reused
  automatically; every other candidate needs manual confirmation.
- Comparison snapshots are cached in
  `state/notion/shared-extras/<data-source-id>/comparison.json` and reused across
  books and resumes; every run still reads the complete inventory and rereads
  only new or changed bodies.

## Resolve suspected duplicates

A suspected duplicate pauses upload before any new write, prints `WARNING` and
writes `extra-review.md` next to the checkpoint, with each candidate's evidence
and ready-to-run commands:

```bash
# Reuse candidate 1 from the report, keeping the existing Notion title and body
uv run book notion resolve-extra --state state/notion/<source-digest>/import.json \
  --extra 1 --use-existing <existing-extra-page-ID-or-URL>

# Or confirm it is separate content to create
uv run book notion resolve-extra --state state/notion/<source-digest>/import.json \
  --extra 1 --create-new

uv run book notion resume --state state/notion/<source-digest>/import.json
```

`resolve-extra` only records the local choice; `resume` rechecks before
uploading. Reuse only adds this book's relation, keeping other book relations
and the user's proofreading and renames. A change in the source, candidate
content or candidate set invalidates the choice and prompts again. Resume never
overwrites verified bodies.

Extras from images are transcribed per the
[Codex image transcription workflow](../.agents/skills/book-management/references/image-transcription.md)
and pass the shared formatting rules before being written as editable content,
then fully read back against the formatted copy.
