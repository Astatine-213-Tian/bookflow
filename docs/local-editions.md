# Local input and preparation

All local EPUBs, TXT and agent-created content JSON use the same input and
preparation path. There is no legacy EPUB mode or intermediate EPUB render.
Original input files are preserved. Content selection belongs in reviewed data;
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
      {"start": 7, "stop": 20, "role": "chapter", "title": "第1章", "parent": "正文·上（2008）"}
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

```bash
uv run book-prepare original.epub --review reviewed-ranges.json \
  --run-dir generated/ingest/prepared
```

Preparation refuses stale hashes, gaps, overlaps and unknown output fields.
Repeating unchanged preparation reuses its result; changed source, rules or
options require a fresh run directory. Local output cannot replace its input.

## Compare editions only when requested

```bash
uv run book-compare first.epub second.txt --report generated/edition-comparison.json
```

Comparison evaluates ordered chapter bodies and meaningful repeats. It is an
independent task, not a mandatory import stage. Keep uncertain unique material
for review instead of choosing an edition merely by byte count.
