# Dataset Audit: Keep/Drop/Split Decisions

Generated audit artifacts:

```text
generated/style_research/corpus/
  cleaned_manifest.json
  cleaning_report.json
  cleaning_report.md
  cross_book_passage_report.json
  duplicate_report.json
  splits.json
  texts/<author>/<title>.clean.txt
```

Reproduce with:

```bash
uv run author-style-research corpus-build --stage clean
```

The script normally leaves raw source TXT files under `datasets/raw/` unchanged and
writes generated cleaned copies for style-research use. Corpus curation decisions,
such as removing an ineligible book, are made explicitly in the raw manifest before
cleanup is rerun. Run this stage and verify residue scans before generating masked
or unmasked chunks.

## Core narrative revision (2026-09-25)

The current research TXT excludes complete synopsis (`简介`/`文案`), bonus-story
(`番外`, including TOC-labelled bonus volumes and `特典`), and afterword (`后记`)
sections. Removing only their headings is insufficient: their prose must also
be excluded before chunking and fitting the mask vocabulary. Narrative epilogues
(`尾声`) remain part of the main story.

`workflows.corpus_sections` aligns the source EPUB's TOC ancestry to the existing
TXT using heading/opening-paragraph matches. Punctuation and whitespace differences
are ignored for alignment only; EPUB prose never replaces TXT prose. TXT-only
exports use explicit headings and, where available, an author notice that the main
story has ended and subsequent chapters are extras. Interspersed bonus chapters
end at the next main-story section. Unmatched EPUB entries are recorded for review.

The policy identifier is `core_narrative_sections_v1`. Each cleaned manifest row
records removed spans, their hashes/counts, source EPUB hash, and alignment
exceptions. Span coordinates refer to normalized raw lines, are one-based, and
include both endpoints. Raw TXT and reader EPUB files remain unchanged.

The revised corpus retains 198 books from 50 authors, with 122,342,394 cleaned CJK
characters (previously 128,555,875). The section pass excludes 1,829 spans totaling
6,530,117 CJK characters; this is not the net reduction, because the prior cleaner
already removed some front matter and applied separate decontamination rules.
All 198 books still meet the 50k threshold, and 195 meet the 120k threshold.

Verification includes 115 passing research tests, unchanged hashes for all 394
source files/manifest entries, 14 real-corpus chapter-boundary checks, and retained
fictional game/video descriptions containing the word `简介`. The 27 input bindings
of the previous iteration-5 pilot also match the preserved snapshot when resolved
through `generated/corpus_cleanup_20260925/historical_input_mapping.json`.

Existing book-level split roles are preserved during rebuilds; newly ineligible
books are excluded and new books require explicit assignment. The mask plan binds
the cleaned text hashes, preventing reuse after another cleanup revision.

The local pre-cleanup corpus and all seven chunk views are preserved under
`generated/corpus_cleanup_20260925/before/`. Historical experiment scores, including
iteration 5, describe their frozen pre-cleanup inputs; they are not re-evaluations
on this revised corpus. See the current generated cleaning/chunk reports for the
new counts and the local cleanup verification report for source-integrity checks.

## Pre-revision result

- Manifest books: 198
- TXT files present: 198
- Missing TXT files: 0
- Authors: 50
- Usable books at `>=50k` cleaned CJK characters: 198
- Primary books at `>=120k` cleaned CJK characters: 195
- Authors with at least 3 books: 50
- Authors with at least 5 usable books: 4
- Exact duplicate cleaned texts: 0
- Punctuation normalization: `canonical_zh_v1`
- Books changed by punctuation normalization: 195
- Repeated cross-book passage fingerprints removed: 1,362
- Books affected by cross-book passage removal: 28
- Lines removed from generated clean copies: 4,877
- CJK characters removed from generated clean copies: 222,241
- Remaining checked cross-book fingerprints: 0

The source TXT files contain many author notes and some scrape/source boilerplate,
but the generated cleaned copies remove detected chapter headings, author-note
blocks, URL lines, and obvious boilerplate lines. A residue scan over the generated
cleaned texts found no hits for the main checked patterns. Cleanup also canonicalizes
equivalent Chinese/ASCII punctuation forms while preserving punctuation roles;
numeric forms such as `3.14` and `12:30` remain intact.

The cross-book decontamination pass removes exact long passages shared by different
books, including copied recommendations, source messages, and other repeated prose
that survives line-level boilerplate rules. It operates only on generated clean
copies. Files under `datasets/raw/` remain unchanged.

```text
作者有话要说
晋江文学城
jjwxc
请收藏
霸王票
营养液加更
最新网址
返回目录
手机阅读
http(s)://
www.
```

## Keep

Keep in the first author-identification benchmark:

- authors with `>=3` usable books;
- books with `>=50k` cleaned CJK characters;
- generated cleaned TXT copies, not raw `datasets/raw/*.txt`;
- raw author/source metadata in `cleaned_manifest.json` for audit and stratified
  analysis.

Use `>=120k` cleaned CJK as the stronger "primary full-length" marker when a method
needs longer stable samples, but do not discard `50k-120k` books from the first
exploratory benchmark.

## Length Tiers

Keep the three books between 50k and 120k (`black_di/白日梦`, `black_di/陌上花`,
and `酱子贝/我喜欢你男朋友很久了`) in the usable set but outside analyses that
explicitly require the stronger 120k marker.

Authors with fewer than three books were removed from `datasets/`; no one-book or
two-book author remains in the current manifest.

## Split Policy

Use book-level splits only:

```text
train: model fitting
dev: model selection, masking threshold tuning, prompt-method tuning
test: final author-identification report
proxy_transfer: held-out target-author books for style-transfer proxy tasks
```

Never split chunks from the same book across train/dev/test.

Current generated split counts:

- train: 88 books
- dev: 53 books
- test: 53 books
- proxy_transfer: 4 books
- excluded: 0 books

The proxy-transfer holdout currently uses four large target-author books:

- `骑士之歌`
- `天宝伏妖录`
- `万物风华录`
- `清平梦华录`

These should not be used to train the author-style identifier if we use them for
style-transfer method selection.

## Do We Need More Data?

For the first exploratory author-identification benchmark: no, the dataset is enough.

For a robust publishable or production-quality method comparison: yes, more books
would help. The bottleneck is not number of author labels; it is books per comparison
author.

Priority:

1. Add more books for existing comparison authors with exactly 3 usable books.
2. Aim for at least 5 usable books per core comparison author, so each author can
   have more than one training book after dev/test split.
3. Prefer same-domain hard negatives: fantasy, historical, xuanhuan, unlimited-flow,
   modern supernatural, gaming/e-sports, and dialogue-heavy danmei.
4. Add new authors only if each new author can contribute at least 3 usable books.

Current comparison depth is:

- `>=3` books: 50 authors
- `>=5` usable books: 4 authors

Most comparison authors still contribute only three books, so their split remains
one train book, one dev book, and one test book. The 50-author classifier therefore
uses strict book-level generalization; transfer-method selection is restricted to
the much deeper target-author corpus.

## Next Step

After the cleaned corpus passes residue checks, build chunk and masking artifacts
from `generated/style_research/corpus/texts/`:

```bash
uv run author-style-research corpus-build --stage all
```

Current generated chunk artifacts:

```text
datasets/unmasked/chunks.clean.jsonl
datasets/masked/chunks.train_global_masked.jsonl
datasets/masked/chunks.entity_masked_v3.jsonl
datasets/masked/mask_terms.json
datasets/masked/masking_report.md
```

Current chunk counts:

- books chunked: 198
- clean chunks: 87,137
- train-global-masked chunks: 87,137
- global-plus-local entity-masked chunks: 87,137
- train chunks: 24,796
- dev chunks: 23,642
- test chunks: 35,994
- proxy-transfer chunks: 2,705

Run the mask-quality QA report:

```bash
uv run author-style-research mask-audit
```

Current QA outputs:

```text
generated/style_research/benchmarks/mask_quality_samples.md
generated/style_research/benchmarks/mask_quality_stats.json
```

Current QA result:

- all three current benchmark views have matching rows and split assignments;
- known scrape and author-note residue hits: 0;
- malformed placeholder chunks in current benchmark views: 0;
- `train_global_masked` uses a 12,000-term content vocabulary fitted from the
  88 training books only and masks about 3.36% of CJK positions;
- `entity_masked_v3` adds terms selected independently from each book by the
  same author-label-blind rule and masks about 18.87% of CJK positions;
- both current masked views use length-preserving `某`, so clean and masked
  chunks retain identical CJK length;
- neither global vocabulary fitting nor transformation reads development,
  test, or proxy-holdout corpus statistics.

The global-only view is an ablation control. A large gain after adding the
per-book supplement would indicate that the masking transform itself may create
an authorship shortcut, so both results must be reported together.

The current reproducible exact n-gram benchmark command is:

```bash
uv run author-style-research authorship-supervised \
  --views clean,train_global_masked,entity_masked_v3 \
  --masked-view entity_masked_v3 \
  --methods char_ngrams \
  --classifiers sgd_hinge,sgd_hinge_unbalanced \
  --char-min-df 20 \
  --output-dir generated/style_research/benchmarks/author_style_supervised_50authors_cleaned
```

Current benchmark and transfer-research reports:

```text
docs/reports/02_authorship_style_meter.md
docs/reports/03_transfer_iteration1_prompt_methods.md
generated/style_research/benchmarks/author_style_supervised_50authors_cleaned/supervised_author_baseline_results.md
generated/style_research/benchmarks/author_style_supervised_50authors_cleaned/supervised_author_baseline_results.json
```
