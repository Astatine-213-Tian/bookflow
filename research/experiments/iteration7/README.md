# Iteration 7: expanded source-aware reading

This extends the frozen Iteration 6 comparison to 50 fresh passages. The four
methods, training references, and one admitted wording correction stay unchanged.
It collects human preferences through a local four-column reader; it does not
change production translation or claim an improvement before those preferences exist.

Run from `research/`:

```bash
uv run --no-sync python -m experiments.iteration7.study prepare
uv run --no-sync python -m experiments.iteration7.study run --workers 8
uv run --no-sync python -m experiments.iteration7.study verify
uv run --no-sync python -m experiments.iteration7.reader --port 8767
```

Open the printed loopback URL. The reader shows author Chinese directly above four anonymous candidate columns.
The English source is retained in the dataset but omitted from the page at the
user's request. New feedback records `english_visible: false`; existing feedback
retains its original viewing state. Local wording differences
can be highlighted. Click a preferred candidate, enable ties, choose none, skip,
or add an optional note. Feedback saves automatically under
`generated/style_reading50_20260925/human_feedback/`; export is also available.
The server must remain running to save to disk. Failed saves stay in that browser's
local storage and are retried when reopening the page. A restarted server should
use the same port to recover browser-only pending feedback.

The old six appear in a separate batch and retain their original A–D mappings.
Each new group has its own frozen A–D mapping. No letter has a global method meaning.
An earlier unlocalized “candidate A feels better” comment is not assigned a scene
or counted as a vote here; its original record remains in Iteration 6.

Independent alignment review supplies exact, hash-bound display crops in
`audit/display_crops.json`. The reader verifies them against unchanged gold text.
Do not modify frozen source/output manifests or crop records after collecting votes.
Votes bind the displayed source and every candidate's output hash, so changed
displays require new judgments. Machine boundary notes are not presented as facts.

For UI tests, start a separate server with `--feedback-dir PATH` pointing under
`browser_qa/`. Test clicks must never enter `human_feedback/`. The source-visible
reader is not a fully blind evaluation, and 50 passages from two historical books
do not establish transfer to other genres. See the
[canonical report](../../docs/reports/09_transfer_iteration7_expanded_reading.md).
