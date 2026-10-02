# Transfer Iteration 10 Direct and positive example translation

2026-10-01. This study returns to the direct and positive-example methods from
the four-arm reader, following the user's dissatisfaction with both editing
variants in Iteration 9. All 48 new paired passages are generated for the user to
choose between these two original generation methods. It does not introduce a
new rewriting stage or establish a preferred production method.

## The two methods

| Method | Frozen generation contract |
| --- | --- |
| Direct | English scene, flanking context and authentic bilingual examples from other books; generate the complete Chinese scene once. |
| Positive | The same inputs and direct prompt, plus the original positive-example instruction and the accepted wording example's English support and corrected Chinese fragment. |

The prompts are reused from `experiments/iteration6/prompts.py`, including its
import of the original direct prompt. The positive bank still contains one
accepted correction. Authentic reference material is filtered by target book
in both arms. No before-text, contrast rationale or Iteration 9 diagnostic card
enters the positive input. Both use the previous generator, `gpt-5.6-sol`, the
same output schema and high reasoning setting.

Each method generates independently from English. This differs from Iteration 9,
whose two editors shared an already-generated Chinese draft. Here there is no
local editor, structural editor, semantic-patch verifier or corrective QA after
generation. Saved candidates are the raw generation results. An independent
source audit observes them without changing them.

The earlier 21 single preferences split into 8 edited, 6 direct, 6 positive and
1 contrastive. These were partial observations, not proof that edited was best.
The user requested more comparisons between the two methods with six selections;
increasing the number of reading examples does not change their training-example
bank. Earlier preferred texts and feedback stay intact.

## Sampling and source boundaries

Seed `2026100110` fixes 48 passages across the six available books, eight each:
乱世为王, 相见欢, 星盘重启, 江湾路七号男子宿舍, 定海浮生录 and 天宝伏妖录.
The existing main-story frame excludes introductions, extras and afterwords.
Main-story fractional subdivisions remain grouped with their parent chapters.
Numeric linked endnote markers are normalized before sampling.

All Iteration 6 mining/development passages, Iteration 7 and 8 reader passages,
Iteration 9 pairs, authentic references, and their two-paragraph contexts are
excluded. There are 5,760 eligible windows in the resulting frame. Books receive
equal quotas; available volumes within a book receive equal quotas; distinct
chapter groups are sampled uniformly, then one eligible window within each
selected chapter. The sampled probabilities are saved with each draw.

Every block of six contains all six books. The first 12 contain two per book,
with each method at A once per book. The remaining 36 contain six per book and
three placements per method at A. All 48 were allocated before generation;
quality never determines which scene appears or where it is placed.

These are fresh passages in previously exposed books and possibly chapters.
The estimand weights books, volumes and chapters equally within the stated
design; it is not uniform over all author words or an unseen-book evaluation.

The target author's Chinese is supplied only to a separate alignment task and
the reader. Boundary quotes must reconstruct literally from contiguous source
lines. Non-high-confidence alignment stops for source review; it cannot become
a format-only retry. A literal-boundary repair, if required, retains the initial
response and cannot change its selected start/end lines or confidence.

## Independent evaluation and evidence

Private artifacts are under `generated/style_direct_positive48_20261001/`.
`manifest.json` binds inputs, source files, method code, mappings and draws.
`output_manifest.json` binds completed raw calls, requests, outputs, gold and
read-only evaluations. `audit/final_review.md` records independent verification
of actual packets, sampling, source boundaries and output identities.

The final evaluator uses `gpt-5.6-terra` in an isolated task, seeing English,
context and anonymous R1/R2 translations. It sees no target Chinese, method
names, prior votes or generation notes. Candidate order is balanced. Its wording
and semantic allegations are diagnostic, not confirmed errors or a style score.
They do not authorize repairs, favorable resampling or automatic selection.

## Reader and feedback

The reader defaults to all 48 groups. Author Chinese, candidate A and candidate B
appear in one row; English is absent from the payload. Highlighting marks local
wording differences, not correctness. A/B positions vary by sample. The user can
choose a candidate, tie, neither or skip, and leave an optional autosaved note.
Reading range, book filter, current sample and highlighting persist on reload.

Votes bind this batch, sample, both candidate hashes and the exact author display.
Previous four-arm and structural-pair votes are exported as separate archives.
Synthetic browser feedback uses its own directory and never counts as human
preference. A stale output/display identity is rejected rather than reassigned.

## Completion and verification

All 96 candidate outputs and 48 source-only evaluations are complete, from 192
saved model calls. The input manifest has 303 bindings and the output manifest
has 626. There were no format repairs or recorded transport failures. The
independent audit checks the actual legacy prompt/payload contract and raw output
identity, not merely the intended code path.

All 48 source boundaries were inspected. One displayed source crop, `dp_036`,
originally included actions already covered in preceding English context. A
hash-bound literal crop in `audit/display_overrides.json` removes that lead-in;
the raw gold, its incorrect edition note and both candidate outputs remain
unchanged. Other edition differences and evaluator quotation limitations are
recorded by the independent audit and are not treated as proven style defects.
The evaluator has four nonliteral quotation flags, and its only major allegation
concerns a character-name correspondence contradicted by the aligned Chinese
source. Its aggregate counts therefore cannot determine the preferred method.

All 153 portable research tests pass. The maintained runner separately excludes
one historical native-Codex test requiring its original installation. JavaScript
syntax checks and dedicated Chrome browser checks pass. Browser checks cover
all 48 groups, book and reading-range filters, three-column layout, highlighting,
preferences and special choices, notes, navigation, reload, persisted view
settings, source-crop readback and export. The two synthetic feedback records
live only in `browser_qa/feedback/`; real new human feedback is empty at handoff.
Both older feedback files retain their original hashes and 23/2 record counts.

## Interpretation

The endpoint is the user's reference-visible preference between the two
unchanged methods. Compare per-book completion and preferences, preserving ties
and neither choices; do not let incomplete reading silently change book weights.
The study has one reader, six selected books and one generation per method per
scene. It does not measure repeat-generation stability, establish 48 independent
books, or prove restoration of the original author's voice.

Reproduction and reader commands are in the
[iteration README](../../experiments/iteration10/README.md).
