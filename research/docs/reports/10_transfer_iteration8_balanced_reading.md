# Transfer Iteration 8: redistribute the reading task to 48 passages

The user requested about 50 groups in total, distributed across more of the
available works. This replaces the previous two-book main reading allocation
with six books × eight passages = 48 groups. Older artifacts and feedback are
preserved separately, without adding them to the reading workload.

## Allocation and estimand

| Work | Downloaded volume coverage | Passage allocation |
| --- | --- | ---: |
| 乱世为王 | Volume 5 | 8 distinct chapters |
| 相见欢 | Volumes 1–4 | 2 distinct chapters per volume |
| 星盘重启 | Single volume | 8 distinct chapters |
| 江湾路七号男子宿舍 | Volumes 1–2 | 4 distinct chapters per volume |
| 定海浮生录 | Volumes 1–4 | 2 distinct chapters per volume |
| 天宝伏妖录 | Volumes 1–4 | 2 distinct chapters per volume |

《江东双璧》 remains a reference book because the only strictly admitted wording
correction comes from it. Evaluating it while removing all same-book examples
would remove the correction treatment itself. Six books supply historical,
contemporary, speculative, and fantasy material without that inconsistency.
The selection is purposive at the book level; it does not represent every genre
or the prevalence of genres in the author's complete works.

The private study is `generated/style_reading48_20260926/`. The 16 EPUB files
contain 453 indexed chapter records. Two fractional main-story subdivisions,
Riverbay 14.5 and Dinghai 90.5, are merged into their integer chapter sampling
units, yielding 451 chapter groups. They are not classified as extras. EPUB
spine intervals include intervening image-split prose and exclude non-story
navigation entries. Chinese ranges are alignment search regions, not assumed
paragraph equivalences.

Seed `2026092608` fixes the draw before generation. The frame contains 6,207
paragraph windows, of which 6,028 are eligible after excluding old Iteration 6
and 7 targets, authentic reference passages, and two-paragraph contexts. Within
each volume, sample the fixed quota of distinct chapter groups uniformly without
replacement; within each selected chapter, sample one eligible window uniformly.
Windows contain complete English paragraphs with a target of 230 words and the
existing short-tail merge rule. Selected samples do not depend on translation
quality or the earlier user's choice. The selected targets contain 11,999 English
words in total, median 245.5 and range 127–361; the shorter target is an eligible
chapter-tail window, not a shortened output chosen after reading results.

The estimand gives equal weight to the six books, equal weight to downloaded
volumes within each book, equal weight to eligible chapters within volume, and
uniform eligible windows within chapter. The inclusion probabilities q/C × 1/W
are recorded. Because per-book counts are eight and per-volume quotas are equal,
each sampled comparison contributes 1/48 to a complete-data mean for that target.
It is not a word-weighted mean over complete novels, and 48 passages do not
constitute 48 independent books. Changing this estimand requires reweighting;
results should not be silently reinterpreted as whole-author prevalence.

Each six-group reading block contains all six books in a seeded random order.
Within each book, two randomized Williams blocks balance candidate order: every
method occupies each A–D position twice, and each directed adjacent method pair
occurs twice. Each method therefore appears 12 times in each position overall.

## Methods and evidence boundaries

The same four Iteration 6 methods and models are retained: direct translation,
positive correction example, contrastive correction example, and Chinese-only
editing followed by English semantic QA. The target Chinese is used only for
alignment and reader display, never for generation, editing, or QA. Tools and
repository access remain disabled inside the isolated model runner.

For Riverbay targets, the Riverbay authentic example is withheld. All four
methods within that book share the same remaining Twin Jades reference and the
same correction bank; other books retain both authentic references. Thus the
comparison is matched within each passage, while baseline example count differs
by book. This should be disclosed rather than interpreted as an identical
reference dose across all six works. No correction bank was expanded here.

Dinghai and Tianbao previously had test/proxy roles in the historical corpus.
`exposure_ledger.json` records their new use for exploratory human comparison.
The original split files and historical reports remain unchanged, but future
methods tuned on these judgments cannot call these books untouched test data.

All 48 targets are newly drawn outside previous probe regions. The earlier
preference for candidate C on `new50/new_001` remains attached to that original
four-candidate comparison. It is not forced into the new draw, remapped by letter,
or included in the new progress count. Export preserves old and new feedback as
separate collections.

The LSWW source includes one literal `[Text Break]` packaging marker in
`balanced_009`. Candidates render it as a scene separator or omit the separator;
no literal translated packaging label appears. Preserve the frozen outputs and
do not classify separator typography as a wording defect.

## Reading and analysis

The page contains only the 48-group task, with an optional book filter. Author
Chinese is visible, English is hidden, and the four candidates remain on one row.
Wording highlights are reading aids, not error labels. Clicking saves preferences,
ties, dissatisfaction, skips, and optional notes with exact candidate/display
hashes. Automated feedback is isolated from human feedback.

Report participation and preferences by book first. With incomplete feedback,
show missingness and skips explicitly; do not treat the user's first-read subset
as a random sample or let heavily rated books dominate an overall result. The
registered analysis plan is stored separately beside the frozen study manifest.
No method winner or style-restoration percentage is implied by this allocation.

Execution and final validation evidence are recorded in `completion.json` and the
private `audit/`, `structure/`, and `browser_qa/` directories. Reproduction commands
are in [`experiments/iteration8/README.md`](../../experiments/iteration8/README.md).

## Completed run and verification

All 48 targets completed, yielding 192 final candidate translations and 48 editor
intermediates from 288 successful model calls. Independent audits replayed the
sampling and balanced mappings, checked source extraction and prompt isolation,
and reviewed all 48 Chinese alignment boundaries. Ten exact-source display crops
shorten source-line boundaries; they are hash-bound and do not rewrite prose.

The 131-test research suite passed. Browser checks visited all 48 groups, verified
exact candidate and author text readback, confirmed four columns remain on one row,
and checked every book filter has eight groups. Real test clicks exercised saving,
revision, ties, skips, notes, reload persistence, method reveal, and export, using
only the isolated test feedback directory. Previous feedback exports match the
original saved records. No human votes or method winner were created by testing.
