# Iteration 9: paired structural editing

This study compares the previous local-editing pipeline with a new structural
patch editor and semantic-patch QA. Each pair starts from the same direct draft.
The intervention changes examples, editing and QA together; it does not isolate
the effect of any one rule. No improvement has been established.

There are 48 fresh passages from six previously exposed books, eight per book.
The default reading range is the first 12, two per book. All 48 samples, outputs
and anonymous A/B assignments were fixed before receiving new feedback. The
author's Chinese and the two candidates appear in one row; English is absent
from the reader payload. Local highlights show differences, not correctness.

Run from `research/`:

```bash
uv run --no-sync python -m experiments.iteration9.study prepare
uv run --no-sync python -m experiments.iteration9.pipeline --workers 12
uv run --no-sync python -m experiments.iteration9.summarize
uv run --no-sync python -m experiments.iteration9.reader --port 8770
```

The existing preparation and generation manifests verify frozen inputs/outputs
on resume. Do not edit their hash-bound code or use the same directory for a new
method. Keep raw calls and unsuccessful repairs. Private artifacts are under
`generated/style_pair48_20260927/`; read the
[canonical report](../../docs/reports/11_transfer_iteration9_paired_structural_editing.md)
for sampling, independent checks, semantic caveats and interpretation.

Votes bind this batch, both output hashes and the exact author display. Previous
four-arm votes remain archived separately and are included separately in export.
Browser QA must use a separate directory:

```bash
uv run --no-sync python -m experiments.iteration9.reader --port 8772 \
  --feedback-dir generated/style_pair48_20260927/browser_qa/feedback
```

Keep the reader process running for disk saves. Browser-pending votes retain
their original display identity and retry on reopening the same URL. Changing
the method after first-12 feedback requires a new version; do not pool it with
this frozen experiment. The current candidates remain unmodified even when the
final evaluator raises a concern.
