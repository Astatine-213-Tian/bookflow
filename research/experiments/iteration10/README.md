# Iteration 10 Direct and positive example translation

This reader compares the two methods that each received six single preferences
in the earlier four-arm study. Their generation prompts, examples, schemas and
model remain unchanged. Both generate a complete scene independently from the
same English and context; positive additionally receives the original accepted
positive wording example. Neither output passes through a later editor or
corrective semantic QA.

There are 48 fresh passages, eight from each of six books. English targets,
reference exclusions, sampling probabilities, reading order and anonymous A/B
assignment were fixed before generation. More examples means more reading
comparisons, not expansion of the prompt's example bank.

Run from `research/`:

```bash
uv run --no-sync python -m experiments.iteration10.study prepare
uv run --no-sync python -m experiments.iteration10.pipeline --workers 12
uv run --no-sync python -m experiments.iteration10.study verify
uv run --no-sync python -m experiments.iteration10.reader --port 8771
```

Resuming verifies input and cached-request hashes. Do not edit frozen generation
code or replace selected passages based on quality. Author Chinese is used for
alignment and display only. The final source-only evaluator records concerns
without rewriting, ranking or dropping candidates.

The page defaults to all 48 groups, with original Chinese and candidates A/B
in one row. Local differences are highlighted. Scope, book filter, current
sample and highlighting survive reload. Candidate methods remain anonymous;
A/B identities vary by sample and balance within each book. Prior four-arm and
structural-pair feedback remain separate archives and do not count as new votes.

Keep the server running for disk saves. Pending browser votes retain their
original output/display identities and retry when the same URL is reopened.
Browser testing must use its own feedback directory:

```bash
uv run --no-sync python -m experiments.iteration10.reader --port 8773 \
  --feedback-dir generated/style_direct_positive48_20261001/browser_qa/feedback
```

Private evidence lives in `generated/style_direct_positive48_20261001/`.
The [canonical report](../../docs/reports/12_transfer_iteration10_direct_positive_reading.md)
records the allocation, independent audit, completed checks and interpretation.
