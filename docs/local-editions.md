# Local input and preparation

Local EPUBs, TXT and agent-created JSON share one preparation path that preserves
the original input. Content selection belongs in reviewed data;
reusable extraction fixes belong in `src/inputs/`.

```bash
uv run book-prepare original.epub --run-dir generated/ingest/reviewed
uv run book-ingest generated/ingest/reviewed/source.json --mode epub --mode notion \
  --run-dir generated/ingest/final -o books/作者/书名.epub
uv run book-ingest original.txt --title 书名 --author 作者 --mode txt \
  --txt-output books/作者/书名.txt
```

`book-prepare` saves schema-validated `source.json`, optional cover bytes and
`report.json`. Inspect normalization findings before upload. Enrichment is
explicit: add `--enrich-metadata` to fill missing values; add `--official-outline`
to use a reviewed official directory. `--chapter-aliases` can resolve known title
differences without rewriting the chapter body. `--chapter-layout` applies
exhaustive reviewed splits after extraction, using stable chapter IDs.

The [content contract](content-json.md) describes agent JSON. For images, use
Codex vision and the maintained coverage/double-reading procedure. For irregular
TXT, a session may resolve structure into that same JSON. Script uncertainty is
a reason to inspect and supply a reviewed result, not to discard difficult text.

Review hierarchy separately from normalization. For a source with 卷 → 回 → 章,
Notion can represent the volume as `所属标题`, each 回 as a chapter row, and its
题记/章 labels as H3 headings within that row. Confirm the intended reading units
from the source and user instructions; do not concatenate all levels into the
volume label merely to fit Notion's one-parent limit. Preserve every body block
and original ordering when combining reading units.

## EPUB inventory and review

EPUB 2/3 navigation, spine, fragments, metadata, CSS emphasis/alignment and covers
are handled by one extractor. Missing or contradictory coverage and body images
require an explicit decision. First inventory the EPUB:

```bash
uv run book-prepare original.epub --inventory --run-dir generated/ingest/inventory
```

`inventory.json` lists every spine page's blocks, anchors and TOC, plus the input
SHA-256. Create a review JSON with that hash and an entry for every listed page:

```json
{
  "sha256": "SHA256_OF_ORIGINAL_EPUB",
  "pages": {
    "Text/body.xhtml": [
      {"start": 0, "stop": 3, "role": "omit", "reason": "Reviewed copyright and 制作 pages"},
      {"start": 3, "stop": 7, "role": "intro", "title": "简介"},
      {"start": 7, "stop": 20, "role": "chapter", "title": "第一章", "parent": "正文·上（2008）"}
    ]
  }
}
```

Ranges are zero-based and half-open; they must be consecutive and account for
every block. Roles include `intro`, `chapter`, `afterword`, `extra`, `omit`.
An omission needs a reason. `parent` supplies a volume title. Optional top-level
`metadata` overrides are validated against the shared schema. A part can contain
`replacements` with absolute block `index`, exact `expected` block and replacement
`block`, for reviewed image transcription or a confirmed extraction repair.
Resolve ambiguous number/title boundaries during this review: `卷一万物复苏`
could be misread as volume 10000. Once the source confirms volume 1, supply
`卷一 万物复苏` or `第一卷万物复苏`; shared normalization produces `卷一·万物复苏`.

```bash
uv run book-prepare original.epub --review reviewed-ranges.json \
  --run-dir generated/ingest/prepared
```

Preparation refuses stale hashes, gaps, overlaps and unknown output fields.
Repeating unchanged preparation reuses its result; changed source, rules or
options require a fresh run directory. Local output cannot replace its input.

## Compare editions only when requested

```bash
uv run book-compare first.epub second.txt --report /private/tmp/bookflow-edition-comparison.json
```

Comparison evaluates ordered chapter bodies and meaningful repeats. It is an
independent task, not a mandatory import stage. Keep uncertain unique material
for review instead of choosing an edition merely by byte count.

## Review possible quotations

EPUB extraction retains source classes/CSS and paragraph locations in separate
`evidence.json`. A bounded scanner selects unusual typography and explicit
attributions. Preparation asks Codex to classify these candidates; only a
high-confidence `quote` changes a paragraph's type. Other judgments preserve
text and formatting, with uncertainty recorded in `quote-review.json`.
No arbitrary `.center` or small-font class is treated as a quotation by itself.

`book-prepare FILE --scan-quotes --review ranges.json --run-dir generated/ingest/review`
writes `quote-candidates.json` without calling a model. An agent session can
supply exact, fingerprint-bound decisions with `--quote-review decisions.json`.
The default workflow uses the locally authenticated `codex exec`, caches validated
batches and resumes without repeating successful judgments. It does not require
an API token. The model can classify only: missing/duplicate IDs, rewrites and
stale decisions are rejected.

Use a fresh run directory when changing candidate decisions; the prepared cache
also binds those decisions. `--quote-review` is available on `book-ingest` for
local files. For direct crawls, save `source.json` first and run `book-prepare`
on that file when a semantic quotation review is needed.

EPUB 2/3 links and declared footnotes are extracted before normalization.
A unique incoming note reference can repair a missing return anchor; repairs
are recorded in the source evidence. Other broken targets require review.
A reviewed `link_overrides` mapping uses `{href: NEW_TARGET_OR_NULL, reason: ...}`
per exact source destination. Null keeps the visible text and omits only a
proven-broken link. Use a guarded block replacement when only one occurrence is
incorrect; never retarget all same-URL occurrences from one textual guess.

## Existing EPUB maintenance

`book-normalize FILE --check` audits an existing archive; omit `--check` only for
an explicitly requested repair. This maintenance command optionally enriches
metadata, applies shared [text and volume-label rules](normalization.md) and
supported XML repairs, reviews remaining findings with read-only Codex, then
validates again. Block classification (numbered subheadings, lists and quotation
review) runs through `book-prepare`. `--no-metadata` and
`--no-codex-review` disable those optional stages. Ordinary ingestion uses
`book-prepare` and never repairs its source archive in place.

### Reviewed structure

Keep source/user-confirmed volume boundaries and the complete chapter sequence.
A `番外卷` is a main-book volume; standalone extras use the shared-extra workflow.
Do not infer that everything after `尾声`, `后记` or `全文完` is an independent extra.
The source directory and body markers are evidence for reviewed selection.

For an explicitly requested reorganization, use these defaults unless the source
or user specifies otherwise: prologue before the first main chapter, epilogue in
the last main volume, afterword as a separate top-level chapter before a top-level
extras group. Prologue text is readable content, not intro metadata. A reviewed
special parent such as `尾声·标题` can remain a volume-like group.

Moving a confirmed volume marker into the directory permits removing that exact
redundant body marker. Keep prose mentioning a volume. Intro title/author lines
may be omitted only when confirmed duplicate metadata. Merging multipart extras
requires reviewed boundaries, preserves every part under centered numbered H3s,
and updates subsequent numbering consistently. Never merge solely from a suffix.
Duplicate-number warnings may suggest a missing number, but require checking the
actual chapter identities before any rename. Preserve uncertain content.

### Metadata enrichment

Normal preparation with `--enrich-metadata` fills missing fields and preserves
source/user values. Explicit archive metadata repair has a different policy:
`book-enrich-metadata FILE --check --report PATH` proposes authoritative updates.
Inspect `dc:date` as publication date and `dcterms:modified` as edit timestamp.
A verified exact Jinjiang title/author match is primary; KadoKado is a fallback
only after a completed lookup has no defensible match, not after a network error.
A locked row needs a unique masked-title match under the verified author; retain
hidden description/subjects and report ambiguity. Explicit user values prevail.

The repair can write official title/creator, Chinese language, publication date,
source, description and ordered subjects (`耽美`, theme/genre, then time-area).
Jinjiang `〖...〗` series labels map to EPUB collection name and position.
Use the lookup's structured directory only after comparing every volume and
chapter with this edition; title/author agreement alone does not prove its layout.
Record directory lookup failures and edition differences rather than guessing.
Metadata-only repair changes the OPF and edit timestamp, not chapter bodies.

### Archive integrity and verification

- Prefer the maintained commands. A one-off structural patch belongs in the
  archive layer and must parse XML, preserve inline formatting and attributes,
  and synchronize affected XHTML title/headings, `nav.xhtml`, `toc.ncx`, and
  OPF manifest/spine when reading order changes. Normalize confirmed volume
  labels with the shared volume function; do not duplicate numbering rules.
- Back up under `/private/tmp/bookflow-codex-backups/`, preserving the
  path relative to `books/`; do not put backups beside reader outputs. Write a
  temporary archive, validate, and replace atomically. Keep `mimetype` first and
  uncompressed.
- Keep a reader-visible contents page in the spine as well as device navigation.
  EPUB 2 retains NCX and registers a new contents page in manifest/spine/guide.
  Automatic flat-NCX repair only numbers bare main titles after a prologue when
  every NCX/title/heading agrees; special sections remain unnumbered. Nested,
  mixed-numbered or inconsistent layouts require review.
- EPUB 3 uses the literal `epub` namespace prefix for `epub:type="toc"` for Apple
  Books compatibility. Parent entries link to their first child; cover art is a
  thumbnail asset without a separate reading page. Visible chapter/prologue
  headings are centered; numbered subheadings follow the shared content rules.
- Validate ZIP/XML, spine/navigation targets and chapter ordering with
  `uv run python src/cli/validate_epub_chapters.py FILE`. Verify a second pass is
  unchanged. Reports under `reports/normalization/` record fixes, review decisions
  and unresolved findings; source defects must be inspected before dismissal.
