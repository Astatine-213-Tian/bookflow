# Transfer Iteration 7: 50 fresh passages and a source-aware reader

The previous six-passage interface was too small and cumbersome for the user's
comparison. This run adds 50 fresh development passages and displays each group
as four candidate translations in one horizontal row. Both English source and
author Chinese are directly visible. The methods and correction bank are unchanged;
this is an expanded evaluation, not a new translation recipe.

## Data and frozen selection

The private run is `generated/style_reading50_20260925/`. Seed `2026092507`
selects 25 passages each from 《乱世为王》 English Volume 5 (chapters 61–75)
and 《相见欢》 English Volume 1 (chapters 1–20). The frame contains 584 windows;
566 remain after excluding the earlier six targets and their two-paragraph
contexts. Every one of the 35 chapters contributes one seeded random window;
seeded chapter selection supplies 15 additional context-disjoint windows.
New windows and their contexts do not overlap each other or the previous six.
There is no replacement based on output quality.

The new passages total 12,795 English words, with a median of 250 and range
230–322. Twelve numeric superscript footnote markers across the source chapter
frame are normalized away, with exact before/after provenance retained. Original
window boundaries are unchanged. Inputs come from the existing cleaned main-text
corpus and declared development books; no test/proxy book is used.

`manifest.json` binds the source files, sample draws, mapping, old references,
one-example correction bank, prompt code, and isolated runtime. Generation uses
the exact four Iteration 6 arms: direct scene translation, direct plus positive
wording example, direct plus contrastive correction, and Chinese-only editing of
the exact direct draft followed by localized English semantic QA. Target author
Chinese is used for alignment and reader display only, not in generation/edit/QA.

## Completed artifacts and reader behavior

All 50 samples have aligned gold and four final outputs: 200 new candidates.
There are 300 completed model calls, including alignment, and 50 retained
pre-QA editor intermediates. `output_manifest.json` freezes all gold and outputs.
The old six remain separate and unchanged, giving 56 readable groups and 224
candidate displays. A previous candidate-A comment without a known sample is
preserved in the old run and is not converted into a numbered vote.

Independent review replayed every seeded draw and A–D mapping, checked source
re-extraction and prompt payloads, and inspected all 50 alignment boundaries.
Eight Chinese source boundaries need literal display cropping because source TXT
lines extend beyond the English target. These crops preserve exact source
characters, are hash-bound to the gold files, and do not rewrite the author.
Four end within an original sentence; the page labels the source as an excerpt.
Several middle passages received deeper independent comparison. This checks
alignment and integrity, not exhaustive semantic correctness of all 200 outputs.

The local reader supports direct clicks, changed preferences, two-or-more-way
ties, none satisfactory, skip, optional notes, and JSON export. Feedback records
batch/sample identity, local A–D IDs, exact display/output hashes, visible-source
state, highlight/method-reveal state, and timestamps. Revisions update the current
vote atomically and append an event history. Browser-only pending saves are
explicitly distinguished from disk saves. Automated test feedback uses a separate
directory and is excluded from human evaluation.

Highlighting marks short candidate-to-candidate wording differences with shared
local context. It ignores punctuation-only differences and large reorderings;
it is neither a semantic diff nor an error annotation. English/Chinese edition
additions, omissions, and reordering are not classified as translation errors.

## Verification and limits

The 126-test research suite passed, including durable feedback, invalid/stale
candidate binding, cross-origin write rejection, and source-crop integrity tests.
Browser checks rendered every one of the 56 groups, verified exact text readback
against the API, and checked all four candidates stay on one row. Narrow screens
scroll the candidate row horizontally. Real clicks exercised revisions, ties,
notes, reload persistence, method reveal, and JSON export in an isolated test
feedback directory. Frozen study bindings also verify successfully.

No human quality results are claimed by this report. Author Chinese and English
are visible, so judgments are source-aware preferences, with anonymous method
names until reveal, rather than fully blind ratings. Fifty passages remain clustered
within two historical books; they cannot establish broader genre transfer or an
Eternal Gate improvement. This run does not enlarge the one-example bank, change
model weights, or alter the production EPUB pipeline.

Commands and feedback locations are documented in
[`experiments/iteration7/README.md`](../../experiments/iteration7/README.md).

## Reader revision: English source hidden

At the user's request, the page now displays only author Chinese and the four
candidates. English remains in the frozen dataset. New feedback records
`english_visible: false`; existing feedback retains its original viewing state.
The earlier assets and manifest are archived under
`reader_revisions/20260925_hide_english/` in the private run directory.
