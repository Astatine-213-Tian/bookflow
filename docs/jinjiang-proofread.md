# Proofreading an existing edition against Jinjiang

`book proofread` treats the existing edition as authoritative and uses chapters
readable with the logged-in Jinjiang account to add missing blank lines, verify
suspected corrupted characters and complete missing author's notes (作者有话说).
The original can be a Notion work page, an EPUB or a shared `source.json`. When
editions differ, a match is ambiguous or a chapter is locked, keep the original
and record why.

## Usage

```bash
uv run book proofread plan --notion '<work page URL>' --jinjiang '<Jinjiang URL or novelid>' \
  --run-dir generated/proofread/BOOK_DATE
uv run book proofread review --run-dir generated/proofread/BOOK_DATE
uv run book proofread apply --run-dir generated/proofread/BOOK_DATE
```

- Notion uses the project's existing MCP login. Jinjiang uses the existing Arc
  login through `arc-cdp run browser-harness` and never subscribes or buys.
  Expired login, purchase pages, locked chapters and load failures are reported
  separately; when login is needed, log in in the browser and rerun the same
  command, which retries failed chapters.
- Without `--jinjiang`, the original's source property is used; when that source
  is not Jinjiang, name the confirmed same work. `uv run book jjwxc TITLE --author
  AUTHOR` prints Jinjiang's official metadata and volume/chapter directory,
  read-only, for checking.
- For a local original, use `--input original.epub` or `--input source.json`
  instead of `--notion`; the result is the run directory's `candidate.json`, the
  source file is unchanged, and EPUB/TXT are separate output choices.
- `plan` reads remote content only and builds candidates. `review` calls the
  read-only Codex CLI only when there are suspected corrupted characters,
  note image captions or partially missing note candidates; the current session
  may instead fill in decisions in the same format. `apply` makes the confirmed
  layout changes and high-confidence, fully evidenced text repairs, then reads
  back.

## Matching rules

- **Blank lines**: locate through a content index of the whole book and linked
  番外, matching the unique context on both sides of the break; short paragraphs
  borrow context from neighbours. Only add missing blank lines; keep the
  original's extra whitespace, dividers and edition additions. A blank line that
  falls inside one original paragraph, in repeated text or in another structure
  goes to review; never split paragraphs automatically.
- **Spaces**: remove a word-breaking space between Chinese characters only when
  the unique matching reference paragraph confirms it is absent. Never overwrite
  the original's layout with Jinjiang's punctuation or stray spaces.
- **Corrupted characters**: first find mojibake, replacement characters, missing-
  glyph markers and escape residue in the original, then reference candidates;
  ordinary edition differences are not errors. Codex may submit only short,
  unique replacements whose text and surrounding context appear in a readable
  reference; with no match, several matches or large edition differences, keep
  the original.
- **Font obfuscation**: Jinjiang's private-use characters act only as unknown
  characters in layout matching, never as evidence for changing text.
- **Suspect hints**: `plan --flagged findings.json` accepts
  `[{"member":"chapter-0003","index":5,"reason":"这个词疑似错误"}]` to verify
  suspected wrong words made of ordinary characters; `index` is zero-based, and
  member and paragraph come from `original/source.json`.

## Author's notes

- Locate the real Notion page from the chapter's closing text; record existing,
  partially existing and unclear targets separately, never adding duplicates.
- Keep edition differences in existing notes. When a note is partly missing,
  Codex may choose insertion points within it and add only whole lines that the
  reference clearly contains and the original lacks; it can never rewrite or
  delete existing text. Leave unreliable positions or meanings for review.
- Add a missing note at the end of its chapter. Labels, dividers and text of new
  and existing notes follow [NORMALIZATION.md](../NORMALIZATION.md); existing
  notes get text patches only where they differ, keeping links, styles and block
  identity.
- A note ends at a divider, end marker or added edition heading; never process the
  other edition's text after it.

Cleanup rules for Jinjiang notes (only when completing notes; image captions,
links and ordinary thanks in existing text stay):

- Keep only meaningful text; never import images or the site's 霸王票/营养液
  widgets.
- Hyperlinks keep their meaningful label without the URL; skip bare entries such
  as “点我”.
- Captions that depend on removed/broken images go to Codex first; delete only
  whole sentences confirmed to have no standalone value. Leave a sentence that
  mixes in important content and cannot be deleted whole for review.
- When nothing meaningful remains after cleanup, add no note heading or divider.

## Reports and recovery

A run binds the original snapshot, reference content and proofreading rules:

| File | Contents |
| --- | --- |
| `original/source.json`, `original/evidence.json` | Original text, Notion pages and original block identities |
| `reference/source.json`, `reference/evidence.json` | Reference text, access results, notes and raw HTML |
| `plan.json`, `report.json` | Match evidence per location, review items and summary |
| `decisions.json`, `note-decisions.json`, `completion-decisions.json` | Text, note-cleanup and partial-completion decisions bound to this plan's fingerprint |
| `candidate.json`, `result.json` | Candidate edition and the applied-change verification |

Resume in the same directory; an independent new proofread uses a new directory
and rereads current Notion content. Notion write requests and logs live in
`state/notion/proofread/<work>/<fingerprint>/`: rerunning an interrupted `apply`
first observes the remote, recognizes completed steps and never inserts twice. It
stops and keeps its logs when text, chapter identity, titles or the TOC changed;
inspect before continuing.

Acceptance covers original block identity and content, added blank lines/notes,
chapter titles and the manual main-text/番外 order. A successful `result.json`
means only that applied changes read back correctly; unmatched locations stay or
are handled separately per `plan.json`. The command never publishes to Bookshelf
or changes Notion publication properties.

## Implementation boundaries

Jinjiang collection (including raw notes from `#note_str`) is in
`src/crawler/providers/jjwxc/reference.py`; matching and decision constraints in
`src/content/proofread.py`; note plain-text preparation in
`src/content/author_notes.py`. `src/workflows/proofread.py` orchestrates stages,
and `src/notion/proofread.py` makes exact incremental edits to existing pages and
reads back; text decoding and validation use the shared `notion-books`.
Incremental edits only insert empty paragraphs/plain-text notes or modify
existing text objects, keeping native styles, links and unchanged block IDs;
nested structures and complex rich-text replacements use the existing full
manuscript update flow.
