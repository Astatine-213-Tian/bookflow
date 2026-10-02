# Iteration 5: real bilingual scene pilot

This exploratory study withholds the Chinese prose of the entire 2026 LSWW
extra from generation, except a small shared canonical-term glossary. The
English is the input and semantic authority.
It compares the current production method with direct scene reconstruction and
a Chinese content-ledger renderer. Both new methods use authentic parallel
examples from existing training books and may resegment paragraphs.

Run from `research/`: `uv run --no-sync python -m experiments.iteration5.pilot prepare`,
then `generate`, the pre-evaluation validation check, `evaluate`, and `report`.
Local inputs and output evidence live
under `generated/style_reassessment_20260925/`. Preparation freezes the sampling
seed, source hashes, prompts, examples, models, and evaluation contract before
generation. No copyrighted passages belong in tracked reports.

Four scenes from one work provide feasibility evidence only. This compares
bundles of changes; it cannot identify the separate effects of context length,
authentic examples, removal of the neutral draft, and paragraph freedom. Two
blinded LLM judgments are not human judgments. The retired style meter is not
an optimization objective. Existing reserved corpus splits remain unchanged.

Run `uv run --no-sync python -m experiments.iteration5.validate_evidence pre-evaluation`
before judges. It records a validation admission only when all artifacts pass;
run the same module with `final` after judging. This validation-only amendment
was fixed after generation started but before judging, without changing the
generation manifest, prompts, samples or candidates.

`uv run --no-sync python -m experiments.iteration5.build_reading_page` builds
a private HTML comparison without displaying model scores. It renders embedded
line breaks as visible paragraphs without editing the frozen candidate files.
