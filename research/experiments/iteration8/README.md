# Iteration 8: 48 passages across six books

The main reading task contains exactly 48 groups, eight per book. It replaces the
previous two-book reading allocation; old samples and feedback remain archived.
Each group shows author Chinese above four candidate translations in one row.
English is retained for semantic checks but is not shown in the reader.

Run from `research/`:

```bash
uv run --no-sync python -m experiments.iteration8.study prepare
uv run --no-sync python -m experiments.iteration8.study run --workers 8
uv run --no-sync python -m experiments.iteration8.study verify
uv run --no-sync python -m experiments.iteration8.reader --port 8767
```

Sampling is fixed before generation: equal book quotas, equal quotas across each
book's downloaded volumes, uniformly selected distinct chapter groups, then one
uniformly selected eligible window per chapter. Fractional main-story subdivisions
14.5 and 90.5 stay attached to their integer chapters. Old probes, authentic example
passages, and their contexts are excluded; output quality never affects selection.

The sole admitted correction comes from 《江东双璧》, which stays reference-only.
The Riverbay authentic example is withheld when evaluating Riverbay. Within every
book, all four arms share the same allowed reference base. This evaluates the
book-exclusion policy; baseline reference count differs between Riverbay and the
other books. The prompt wording and model configuration are otherwise unchanged.

`generated/style_reading48_20260926/` holds the frozen inputs, generated outputs,
source audits, exact display crops, and human feedback. `exposure_ledger.json`
records that Dinghai and Tianbao are now exposed for this exploratory study;
global corpus splits and historical research artifacts are not rewritten.

Feedback saves under `human_feedback/`. Export includes a separate archive of the
previous batch's feedback. Old preferences are not applied to new scenes or
included in the 48-group progress count. Browser tests use a separate
`--feedback-dir generated/style_reading48_20260926/browser_qa/feedback`.

Keep the server running for disk saves. Pending browser-only saves retain their
original display identity and can be retried by reopening the same URL/port.
Candidate A–D mappings are local to each group and balanced across positions.
Independent source crops must remain literal and hash-bound to unchanged gold.

Interpret the study as book-equal preference over six available works, not an
unbiased sample of all author text or 48 independent books. See the
[canonical report](../../docs/reports/10_transfer_iteration8_balanced_reading.md).
