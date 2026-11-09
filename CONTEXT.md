# Book preparation

A personal library gathers books and later additions from many sources, keeps
their reading structure, and prepares editions for reading or editing.

## Language

**Book**: The work being collected or maintained, identified independently of its
display title and of where it is read.

**Book JSON**: The one content contract every source becomes and every destination
reads (`source.json` in a run directory; see `docs/content-json.md`).
_Avoid_: Source JSON or shared JSON; `source.json` is only its filename.

**Source**: Material used to acquire or correct a book: a website, an existing
edition, a text file or supplied images.
_Avoid_: Import as a name for every acquisition task.

**Search**: Discovering and previewing candidate sources before one is chosen.
_Avoid_: Crawl when only finding candidates.

**Collection**: Retrieving content from a chosen source within an explicit book or
collection scope. A known source, such as a Patreon collection, needs no search.

**Chapter**: A titled reading unit. Introductions and afterwords keep their own
roles, distinct from the first or last story chapter.

**Volume**: An ordered group of chapters under a shared heading.

**Independent extra**: Supplementary content outside a book's main outline,
possibly shared by several books.
_Avoid_: Treating an afterword or a volume named 番外 as an independent extra.

**Normalization**: Agreed corrections to characters, spacing, punctuation and
explicit formatting that keep the meaning and selected content; rules in
`NORMALIZATION.md`.
_Avoid_: Translation, rewriting, source selection.

**Correction**: A reviewed replacement for identified content, based on its
current version and leaving other reading units untouched.

**Destination**: Where a prepared book is written: a local EPUB, a TXT reading
copy or an editable Notion draft.
