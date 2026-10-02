# Iteration 6: a sampled wording-error bank

This private exploratory probe mines real parallel training books for clear
translationese, excluding edition differences and debatable preferences. It tests
the existing direct scene prompt, extra positive examples, contrastive examples,
and a Chinese-only edit followed by localized English semantic QA. It does not
change production translation or train model weights.

Run from `research/`, in order:

```bash
uv run --no-sync python -m experiments.iteration6.resume prepare
uv run --no-sync python -m experiments.iteration6.resume align
uv run --no-sync python -m experiments.iteration6.resume mine
# Independently inspect gold alignment, proposed repairs and rejected examples.
uv run --no-sync python -m experiments.iteration6.resume freeze-bank
uv run --no-sync python -m experiments.iteration6.resume generate
uv run --no-sync python -m experiments.iteration6.resume evaluate
uv run --no-sync python -m experiments.iteration6.results
uv run --no-sync python -m experiments.iteration6.resume verify
```

`generated/style_probe6_20260925/` contains copyrighted sources, the 1,705-window
sampling frame, every seeded draw, isolated model requests/results, all example
admission decisions, frozen bank, anonymous outputs, and independent audits.
Input hashes make resumed runs fail if a frozen source or prompt changes. Model
sampling is nondeterministic; the fixed seed governs corpus selection and blinding.
Use the `resume` entry point for repeat commands: once a stage is frozen it verifies
and preserves the artifacts, including third-review admission decisions. `probe.py`
is the hash-preserved implementation used for the original execution.

Theme quotas are purposive. Chapters and then windows are sampled uniformly within
their declared frames, without quality-based replacement. Both development books
are historical; this run cannot establish modern/speculative transfer or generalize
directly to Eternal Gate. Model error flags/preferences require critical reading;
the reading page intentionally hides machine ratings and method names initially.

The matched-positive arm controls the presence of the same corrected examples,
but contrastive prompts contain more tokens and explicit reasons. The editor arm
has two extra calls. Neither comparison isolates a compute-matched causal effect.
