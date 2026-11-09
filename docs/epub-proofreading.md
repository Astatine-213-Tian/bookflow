# EPUB proofreading: audit, preview, confirm, apply

Proofread a downloaded EPUB book by book: layout, text, cover and
filename/metadata. Tools inventory, propose differences and validate; Codex reads
the context and judges structure and visual result.

## 1. Establish the baseline

Record the original's absolute path and SHA-256, and inventory its EPUB version,
OPF, manifest, spine, NAV/NCX, visible contents page, cover declaration and actual
size, heading levels, CSS, inline styles, links, footnotes, images and fonts.
Settle the scope first; a supplied local EPUB already fixes the output type, so do
not ask for an output format.

The result replaces the supplied file in its own directory by default; a rename
stays in that directory as `书名.epub` (title only). Copy into the repository's
`books/<author>/<title>.epub` only when the user asks. Leave the original
untouched until confirmation. Per [storage](storage.md), one-off probes,
screenshots and previews go in the system temporary directory; unfinished review
lists and decisions go in `generated/updates/<task>/`. On resume, recheck the
original's hash; old decisions never apply to a changed book.

Use the read-only checks from
[existing EPUB maintenance](local-editions.md#existing-epub-maintenance):

```bash
uv run book normalize "INPUT.epub" --check --no-metadata --no-codex-review \
  --report /private/tmp/bookflow-proofreading-normalization.json
uv run book validate-epub "INPUT.epub"
```

Always pass `--check`. Fix counts in the report are proposals, not applied or
approved changes, and zero issues does not mean visual proofreading is done. The
current Codex session reviews flagged items in context. For published books,
metadata evidence is the copyright page of the matching edition (look up the
publisher and similar sources as needed), not the Jinjiang-first enrichment.

Done when: chapter coverage, main layout types, text risks, metadata evidence and
baseline defects are recorded, each traceable to an archive member and
element/paragraph. Call out the workable scope for fixed-layout, scan-only or
complex vertical-text books separately.

## 2. Classify and propose candidates

[NORMALIZATION.md](../NORMALIZATION.md) is the only source of general text rules;
below are the proofreading layout and review decisions it does not cover. Record a
book-specific exception in the review decisions; changing a general rule means
updating the implementation, executable examples and tests together.

### Headings, hierarchy and spacing

Give one semantic level one weight, size, spacing and alignment, and keep levels
distinct. Check every chapter opening; do not infer the level from `h1/h2` or a
single class. Headings are bold by default and inherit the reading theme's color
(fixed black fails in night mode). Use `em` spacing and remove chapter-opening
gaps made of empty paragraphs, repeated `<br>` or fixed heights; scene breaks in
the text are not layout whitespace.

| Semantic role | Preferred candidate | Review focus |
| --- | --- | --- |
| Plain chapter or volume title | Bold, centered, compact opening | Clear separation from the text, never half a page |
| 回目 (回 number + two-line title) | Centered; number slightly smaller, one line per title line | Keep both lines; no spaces faking line breaks; may wrap on narrow screens |
| Title + subtitle + author/publisher | Compact left-aligned title group | Title prominent, credits smaller; centered as an alternative |
| Plain-number sections within a chapter | Slightly bold, compact, left-aligned preferred | Keep the original numbers and order; preview a centered option if needed |
| Chapter/part title above left-aligned numbered sections | Title also left-aligned and bold | Shares one left edge with the sections, as in 《永远的尹雪艳》; overrides the centered default |
| Subheading inside a quotation | Bold within the quotation block, usually centered | Separate from the narrative; never a new TOC chapter |

Adopting the numbered-section option above overrides, for this book, the shared
preparation default (Chinese numerals in a centered H3): list the affected
sections in the review record, and do not afterwards run ordinary preparation that
would overwrite the choice.

A “返回目录” link in a chapter heading, once its target is confirmed to be the
contents page, may lose its link; keep the text, nested formatting and every
referenced `id`/anchor. Only these links: TOC entries, body links, footnotes and
their back-links stay, and note links inside headings get their own review. Check
the color of descendant `span/a` too.

### Table of contents hierarchy

Cross-check NAV, NCX, the visible contents page and spine order, keeping the
book's meaningful volumes, parts, sections and chapters. When the outermost node
only repeats the book title (e.g. a top-level “纽约客” in 《纽约客》) and groups
nothing, remove that level and promote its children one level, keeping their
order and inner hierarchy. A childless duplicate-title entry pointing only at the
title page may leave the TOC; the title page and metadata keep the title. Never
delete by title match: a collection's individual work titles, same-named chapters
with their own content and volume titles stay. Preview the TOC tree before and
after; on apply, update NAV/NCX/contents page, anchors, NCX playOrder and depth,
then validate every target and the chapter order.

### Poems, dedications and quotations

Decide genre and boundaries before style. Classes, centering, indentation and
quotation marks are only candidate evidence; read the surrounding text and, when
needed, the user's screenshots of the original. Split a fused heading/quotation
only at a provable boundary, keeping content and order verbatim. Identify
quotations with [quotation review](local-editions.md#review-possible-quotations).

- **Standalone short poem**: title and author form a compact title group; lines
  centered; punctuation, line breaks and stanzas preserved.
- **Poem inside narrative**: the block is centered as a whole; long or uneven
  lines may be left-aligned within it with indented continuations. Keep a couplet
  together; restore stanza breaks only with evidence from the original, never a
  large gap after every line.
- **Dedication/epigraph**: short lines form one centered block, optionally
  left-aligned inside; compare with a line-by-line centered option. Date and
  signature may be right-aligned; do not pull the previous piece's closing date
  into the dedication.
- **Prose quotation, 花谱小传 biography, letter, notice**: slightly narrower
  margins, left-aligned, near body size. A letter's signature/date may be
  right-aligned; poems inside are handled separately. Ordinary dialogue stays body
  text.

Lay out poems and quotations with block-level CSS, never with runs of spaces,
full-width spaces, fixed pixel widths or code blocks; style each genre separately
rather than giving every quote the same centering, italics, border or small font.
Short poems may avoid page breaks; long quotations must allow them to avoid blank
pages. Text stays visible at larger font sizes; never clip overflow with fixed
heights.

### Punctuation and spacing

Large gaps in a screenshot can come from `text-align: justify`, letter spacing,
full-width punctuation or non-breaking spaces: check the real characters, then CSS
and reader justification, rather than only deleting spaces. Review general text
differences item by item in the `book normalize --check` report.

- Review English sentences and references as local-language segments: once
  confirmed, convert their full-width brackets, colons, commas and semicolons to
  ASCII and tidy word spacing; Chinese narrative and Chinese quotations keep
  Chinese punctuation. The shared normalizer does not do this: record the exact
  before/after snippet and location and make a reviewed book-specific fix.
- English bibliography blocks are left-aligned with natural wrapping; consider a
  hanging indent only when entry boundaries are clear. Keep names, titles,
  volume/issue, year, pages, capitalization, apostrophes, accents and connectors;
  never rewrite a citation format from appearance.
- An original-language parenthetical right after its translation stays in the
  same paragraph; never split it into a quotation block because the language
  changes or the English is long.
- Font differences are not grounds for changing characters. Classical text,
  variant and rare characters and CJK extension characters are valid content:
  confirm they and any variation selectors survive intact, never modernized or
  replaced with common forms. Record suspected typos and edition differences as
  needing collation; record missing font glyphs, tofu/replacement characters
  already in the source, and content errors separately.

### Cover

Run `book cover check` and look at the original and a 120–160 px thumbnail; keep,
crop and restore follow
[cover normalization](../.agents/skills/book-management/references/cover-normalization.md).
A clear cover already at 2:3 keeps its original pixels, never upscaled by
interpolation. When the source has a cover reading page, list its removal from the
spine/cover navigation in the preview; the cover image stays.

### Filename and metadata

A filename is the title plus extension only, e.g. `品花宝鉴.epub`: no author,
download site, slogan, series or edition suffix such as “简体中文版”, and no 《》.
Edition, author and similar information stays in the reviewed metadata or
copyright page. Show old name → proposed name before applying; on a name
collision, check content and edition, then separate by directory or ask the user —
never overwrite or append a suffix.

List `title/creator/language/publisher/date/identifier/description/series` field
by field: current value, proposal, evidence and whether it changes. Remove
confirmed download-site suffixes, slogans and tool ads; URLs in the copyright
page's publisher details, body references and legitimate source records stay. Keep
real subtitles, translators, editions and series; moving “简体中文版” and similar
out of the title is a listed decision too. A missing date stays unknown;
distinguish copyright year, revision, publication and modification dates. Keep
stable book identifiers; never take an EAN, ASIN or UUID for an ISBN. When the
description's chapter count conflicts with the actual chapters, check whether it
counts a preface; never add or drop chapters to match it.

### Advertising and copyright pages

Check front matter, back matter, the TOC and chapter interiors for promotion:
download-site ads, traffic URLs/QR codes, join-a-group text, paid-resource ads
and repeated site credits. Judge by context and source, never by a URL or the word
“版权” alone. Author afterwords, real publication information, acknowledgements,
reference links, copyright notices and real publisher contacts stay. The preview
lists each page/snippet to delete with its reason; deleting a standalone ad page
also updates manifest, spine, NAV, NCX, contents page and image references,
removes only resources used solely by the ad, and keeps content and anchors the
text still references.

Group the copyright page as title, author/translator, edition/series,
publication details, identifiers and notices, compact and left-aligned: title
bold, other fields one size with moderate spacing, labels complete, long
URLs/addresses wrapping naturally, no full-width-space alignment or stretched
justified notices. Legal notices and copyright attribution stay verbatim. Without
evidence, add no date, ISBN or edition; record user-specified metadata separately
from the original page's historical record, never rewriting the page to make them
agree. The copyright page is its own preview type: show original and candidate,
and after applying verify the text is complete and fits a narrow screen.

### Title-page labels and photos

Decorative series badges and typesetter labels on the title page may be removed
at the user's request; they are not automatically ads. Real series information
stays in metadata/the copyright page; body photos and captions are unaffected.

- A photo and its caption form one centered unit, sized by aspect ratio with
  display width, max width/height and spacing: group photos wider, portraits with
  vertical room; never stretch, crop out people or separate the caption.
- Original pixel quality caps the display size; when enlarging a small image,
  state the sharpness limit. Interpolated or generated detail is not a repair.
- When an enlarged photo is clearly blurry, look for the matching photo in the
  same or a reliable edition; check person, composition, crop and caption one by
  one, record source and file hash, and replace only confirmed matches — never a
  photo of a similar-looking person. Without a clear source, display
  conservatively.
- In a batch, check the frontispiece photos of every book, not just the one in
  the user's screenshot.
- When a source caption's date disagrees with the original book, record it as
  needing collation; layout or a replacement photo never authorizes rewriting a
  caption.
- Preview single and group/multi-image pages; verify caption pairing on narrow
  screens, large fonts and page breaks.

## 3. Build previews and wait for confirmation

Show at least one example of each proposed layout change, plus the exceptions
most likely to overflow or be misjudged; typically chapter openings, complex title
groups, numbered sections, poems, long quotations, English bibliography, cover,
filename/metadata table, copyright page and the ad-removal list. Mark types the
book lacks as not applicable rather than borrowing another book's sample.

Previews use the original EPUB's real text, original and candidate side by side,
with the specific change and its location; for a real choice give two options and
say why one is preferred. Compare with the same viewport, font, size and theme,
and note whether the original simulates reader-theme link colors, margins and
similar. Support narrow, wide, large-font, light and dark checks. After checking a
preview, open it in the local browser and give a link to reopen it.

HTML/CSS previews confirm weight, alignment and relative spacing only, not Apple
Books/Readium pagination. For reader checks, build a separate candidate EPUB
clearly marked as a preview in a temporary directory; it never replaces the
original or enters the library. After the browser check passes, the final
candidate still needs a reader check.

The review record holds at least: input hash, preview version, location and
original-snippet check, issue category, candidate change, reason, scope, the
user's choice and open items (a manual record, not a CLI config format). “Confirm
this version” covers only the version and scope shown; a newly found genre or a
changed plan needs a new preview first.

**Stop point: until the user confirms, do not overwrite or rename the original
EPUB, write final library files, replace the official cover, or publish to
Notion/NAS/Apple Books.** Read-only review and preview refinement may continue.
After confirmation, complete the authorized scope without asking again for the
same item.

## 4. Apply, read back and finish

Before applying, check the confirmation record against the original's hash and
check for target conflicts; if the source changed, redo the difference review.
Book-specific edits use exact matching; stop and recheck when the match count is
wrong. For style-only fixes, keep archive members and IDs instead of re-extracting
and rebuilding the whole book; before a rebuild, confirm the shared input can
represent the book's full structure. Apply only confirmed changes: a full
normalization run can bring unapproved numbering/structure changes, so never run it
unconditionally at the end.

Write a temporary EPUB per
[archive integrity](local-editions.md#archive-integrity-and-verification),
validate it, then atomically replace the original (or the location the user
named). When renaming, remove the old filename only after reading back the result
and the backup, so the library holds one version.

Acceptance:

1. `book validate-epub` passes; ZIP CRC, XML, `mimetype`, and every NAV/NCX link
   and anchor are correct.
2. Chapter order, titles and TOC agree; a per-member diff shows body changes only
   from approved punctuation/structure differences. Compare split paragraphs word
   for word to rule out lost poem lines, quotations, repeated paragraphs and
   footnotes.
3. Every changed role has consistent weight, theme color and spacing, with no
   clipping on narrow/wide screens, large fonts or night mode. Check chapter
   openings, poem page breaks, long quotations and footnotes in a reader; mark
   untested platforms as unverified.
4. The cover decodes, its declaration is correct and the thumbnail is legible; the
   final filename matches the OPF title/author.
5. Rerunning the approved transformations produces no new differences; reread the
   final EPUB and record its hash.

The final report separates applied, kept/needs collation and preview-only items,
with final file or preview paths. Text review without a comparison edition is not
a full word-for-word proofread. Afterwards clean temporary files per the storage
rules, keeping previews awaiting confirmation and recovery records.
