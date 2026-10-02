# Transfer Iteration 9: paired structural editing

2026-09-27. All 48 old/new pairs are generated and available for anonymous human
comparison. This is a completed experiment packet, not evidence that the new
method improves author resemblance. No production method or EPUB is changed.

## Question and method

The prior reader's partial feedback favored local editing in 8 single choices,
against 6 each for direct and positive-example translation and 1 for contrastive
translation. These 21 choices were not a decisive winner. Subsequent stage
traces found verbose constructions inherited from direct translation, local
editing that sometimes expanded them, and semantic QA that could restore
literal wording. This motivated a new, explicitly numbered intervention.

Each new scene has one common direct draft, generated with the unchanged legacy
DIRECT prompt and allowed authentic references. The old branch preserves the
legacy EDIT and full-scene semantic-QA prompts, schemas, models, correction bank
and editor-note transmission. The new branch uses:

1. A target-English-blind structural editor, seeing the same Chinese draft and
   provisional style cards from other books. It may reorganize constructions
   within a paragraph, retain casual register and avoid unnecessary explanation.
   It must preserve meaning and can make zero edits.
2. Exact, unique, nonoverlapping paragraph-local patches, deterministically
   applied to the original draft. No whole-scene rewrite follows this step.
3. English-grounded minimal semantic patches, with context but without the
   editor's rationale, reference cards or target author Chinese.
4. A separate verification call accepting or rejecting each proposed semantic
   patch. This uses the generation model in an isolated call, not a human.

Generation uses `gpt-5.6-sol`; semantic QA and final evaluation use
`gpt-5.6-terra`, matching the previous experimental controls. The new method
changes several components together. This tests a postprocessing package,
conditional on one shared draft, rather than the causal contribution of one
card, editor rule or verifier.

The 11 cards are diagnostic hypotheses, not human-approved phrase corrections.
All target-book cards and their supporting contexts are withheld. The shield
card admits only the posture/movement span; a separate lexical-fidelity issue
is excluded from the before/after transformation. Its retained explanatory
reason still mentions that historical lexical issue, a disclosed training-card
limitation. Ambiguous and already-adequate examples retain their uncertainty
and stop-editing labels. Cold, intensity, aimlessness and other English-supported
content must not disappear merely to resemble the shorter Chinese edition.

## Fixed sampling and reading allocation

Seed: `2026092709`. The 453 downloaded main-story records form 451 chapter groups.
The structural frame excludes introductions, extras and afterwords, while
retaining main-story fractional subdivisions with their parent chapters.
Footnotes are normalized before constructing windows. Of 6,207 windows, 5,894
remain eligible after excluding prior mining/development/reader passages,
authentic references and their two-paragraph contexts.

| Book | Full batch | First reading range |
| --- | ---: | ---: |
| 乱世为王 | 8 | 2 |
| 相见欢 | 8 | 2 |
| 星盘重启 | 8 | 2 |
| 江湾路七号男子宿舍 | 8 | 2 |
| 定海浮生录 | 8 | 2 |
| 天宝伏妖录 | 8 | 2 |

Within each book, downloaded volumes receive equal quotas; distinct chapter
groups are drawn uniformly, then an eligible window uniformly within each
selected group. The full study is book-equal, volume-equal and chapter-equal,
not uniform over all author words. These are new passages in exposed books and
possibly exposed chapters, not an unseen-book test.

All 48 targets, reading order and arm assignments were fixed before generation.
Every consecutive six scenes contain all six books. Each book has old-at-A once
and new-at-A once in the first 12, and three each in the remaining 36. No output
quality affected selection or ordering. A method change after the first 12
would require a new version; it cannot be pooled with this run.

## Completed evidence and independent evaluation

Private evidence lives under `generated/style_pair48_20260927/`:

- `manifest.json`: 252 input bindings, sampling draws and registered boundaries.
- `output_manifest.json`: 1,234 bindings covering 351 requests, calls, gold,
  stages, outputs, evaluations and the two format-repair records.
- `summary.json`: deterministic descriptive counts; no style score or winner.
- `audit/final_review.md`: independent review of the actual run.
- `audit/input_verification.json`, `audit/pipeline_verification.json` and
  `audit/reader_verification.json`: independent replay and display checks.
- `browser_qa/verification.json`: isolated browser interaction and readback.

The independent audit replayed sampling, prompt/payload contracts, shared-draft
provenance and patch application. All 48 author-reference boundaries were read
against the English target; all crops reconstruct as literal contiguous source
spans, with no additional crop needed. This checks every boundary, not every
interior proposition in the original books. The new editor received no target
English or target author Chinese. Source alignment was high-confidence on every
raw first response; uncertain alignment was not retried into acceptance.

The new editor proposed 87 patches across 45 scenes and left three drafts
unchanged. New semantic QA proposed 14 patches; verification accepted 2 and
rejected 12. No final old/new pair is text-identical. These are processing
counts, not measures of style improvement.

An additional isolated evaluator assessed each old/new pair under opaque IDs,
seeing English and context but no author gold, method names, editor notes or
human votes. It raised 23 meaning concerns across 18 old outputs and 54 across
32 new outputs, plus 4 and 9 wording concerns respectively. These are **model
allegations, not validated error counts**. They do not support promoting the new
pipeline as a fidelity improvement. They also do not measure author style.

There are concrete limitations behind these counts:

- In pair 019 the evaluator misreads a contextual pronoun and flags both arms;
  the verifier correctly rejects the same proposed repair. Its severe label
  therefore cannot be treated as a verified semantic defect.
- Pair 032 retains a genuine question-scope problem inherited from the shared
  draft. The old branch and the new branch leave different fidelity problems.
  A format-repair retry also changed the proposed meaning; verification rejected
  that proposal, so it did not enter the final text. This is a recorded retry
  scope failure, even though the final candidate was not changed by that retry.
- Pair 038 exposes a totality/hedging boundary that the verifier dismissed.
  High rejection of QA proposals does not certify faithful preservation.
- Pair 048's retry fixed only literal English quotation support; the proposed
  text stayed unchanged and was rejected. Both raw attempts remain preserved.

The generic retry helper can also catch semantic alignment uncertainty, despite
being called a format repair. That path was not exercised for alignment here.
A future iteration should distinguish malformed representation from substantive
uncertainty and enforce semantic invariance of format repairs. Frozen code and
candidates are retained, rather than silently changing this treatment.

## Reader and validation

The reader shows author Chinese, candidate A and candidate B in one row, with
the original always open. English and method labels are absent from its data
payload. Highlighting marks local changes between candidates, not errors.
The default range is the first 12; filters expose all 48 or the remaining 36.
Clicking a preference, tie, neither or skip and writing a note saves locally;
votes bind the exact candidate/output hashes and author display identity.
Previous four-arm feedback is a separate archive, never carried into these pairs.

All 146 portable research tests pass. One historical native-Codex
command-template test is explicitly environment-bound and excluded by the
maintained runner. JavaScript syntax checks pass. Dedicated test Chrome checks
cover the three-column display, first-12/full-48/book filters, highlighting,
selection, revision, tie/neither/skip/clear, note autosave, navigation, reload,
pending-save recovery and export. All synthetic records use a separate feedback
directory; the real paired-study feedback is empty at handoff.

## Interpretation and next step

Ask the user to read the first 12 and select whichever candidate sounds closer
to the original, allowing ties and neither. This is early directional feedback,
not a powered validation trial. Report later preferences and completion per
book, preserve ties/neither and avoid silently weighting partially reviewed
books more heavily. The full study has six purposively selected books, one
reader and one draw of each stochastic pipeline, not 48 independent books.

Any claim of better style needs those new preferences and separate consideration
of fidelity. Semantic concerns remain visible in the research record and do not
trigger favorable resampling, automatic reranking or post-hoc candidate edits.

Commands are in the [iteration README](../../experiments/iteration9/README.md).
