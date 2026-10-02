# Iteration 8 feedback and local style diagnostics

This is post-hoc analysis of the existing six-book, 48-scene reading study,
not another translation method. The first human snapshot contains 21 single
preferences: edited 8, direct 6, positive 6, contrastive 1; one none response;
and one note-only response. The note is not silently converted into a tie.
The sample is partially completed, so these counts are not a population estimate.

## Completed diagnostic result

All 96 model readings completed on their first recorded attempt. Descriptive
pooled 1–5 means are direct 3.60, edited 3.57, contrastive 3.42, and positive 3.29.
Both reviewers tie direct with edited in 41 of 48 scenes. Sol favors direct in
4 and edited in 3 remaining scenes; Terra favors direct in 6 and edited in 1.
The tiny mean difference is not evidence of a stable method advantage.

Against the 21 human single choices, the same unique top choice occurs only
1/21 and 2/21 times. Including tied top tiers raises coverage to 15/21 and 13/21,
which must not be advertised as a validated preference-prediction accuracy.
The two model top-tier sets agree exactly in 12/48 scenes and overlap in 37/48.

All rating structures and independent aggregate recalculations passed. Ten of
372 cited units have punctuation/whitespace differences from exact source spans;
independent normalized checks found no fabricated lexical content in those
citations. However, close review of 18 model readings across nine scenes found
some English-supported intensity or relations treated as author-style drift,
alongside correctly excluded version differences. The score is useful as a
diagnostic aid, not a reliable automatic selection endpoint. No production
method is promoted and proposed card revisions remain untested on fresh scenes.

## Procedure

`evaluate.py prepare` freezes the human feedback, source-visible author crops,
all candidate identities, anonymous reviewer packets, runtime, and rubric.
No human choices, method labels, previous scores, or unverified edition ledger
enter the model packets. Exact rendered duplicates, if present, are collapsed
and reexpanded with identical scores/ranks. None occur in this batch.

Two tool-disabled model readings examine all 48 scenes: `gpt-5.6-sol` and
`gpt-5.6-terra`, with reversed candidate order. Changing model and order together
does not isolate order bias. Each returns 2–4 local cited comparisons plus
ordinal 1–5 judgments for action/clause organization, narrator register,
dialogue rhythm, and explanatory restraint. Unassessable dimensions are omitted
from means. Books have equal weight; 96 readings are not 96 independent scenes.

English is the semantic constraint. Terminology and source-edition additions
or omissions are separated from comparable stylistic form. Shortness, character
overlap, and copying Chinese-only details receive no reward. Individual ordinary
synonyms are not treated as defects. The rubric was motivated by user concerns
and examples 016–018, so human agreement is descriptive, not independent metric
validation. Analysis also reports agreement with those examples excluded.

`analyze.py` validates candidate/ranking coverage and exact quotation membership,
then reports both reviewers separately, pooled descriptive means, pairwise
win/tie/loss, and strict versus tied agreement with human choices. Raw erroneous
citations remain intact and flagged. Sensitivities restrict to reviews with
some valid comparable evidence, and reviews where all quoted units are exact;
neither subset should be mistaken for an unbiased replacement sample.
An exact quote proves provenance, not the validity of a style judgment.

A separately read set of 11 cards spans six books / seven scenes, including
the user's three examples. Cards cite original, edited and English spans and
contain optional source-faithful revisions, a keep-existing control, and an
uncertain example rejected as a definite correction. These are purposively
chosen development examples, not frequency estimates or evaluated improvements.
Once used for prompt design, they cannot be reused as a fresh test set.

The existing editor in `../../iteration6/prompts.py` explicitly limits editing
to clear idiomatic wording problems and asks already-natural sentences to remain
unchanged. Many user concerns are valid but author-distant formulations rather
than clear errors. A subsequent probe should therefore distinguish optional
author-style transformations (action packing, colloquial register, comic timing)
from obligatory corrections, while preserving English-supported facts. These
diagnostics do not establish that the proposed revisions improve unseen scenes.

Five private stage traces distinguish inherited wording from editor expansions
and QA reversions. The current QA input contains the editor's notes as well as
its paragraphs. Separating QA from the editor's justifications is a testable
design option; the traces do not prove that those notes caused a missed defect.

## Local artifacts and reproduction

All source quotations, feedback, requests, raw ratings, audit notes, and the
Chinese comparison page stay in ignored
`research/generated/style_feedback_review_20260927/`. Original study artifacts,
human feedback, reader implementation, production glossary and EPUB are untouched.

From `research/`:

```bash
uv run --no-sync python -m experiments.validation.style_feedback.evaluate prepare
uv run --no-sync python -m experiments.validation.style_feedback.evaluate run --workers 8
uv run --no-sync python -m experiments.validation.style_feedback.analyze
uv run --no-sync python -m experiments.validation.style_feedback.report
uv run --no-sync python -m unittest tests.test_style_feedback_analysis
```

The report command also needs the privately audited
`close_reading/comparison_cards.json`. It creates a standalone `review.html`
with four columns and visual change highlights; the English source stays out
of the rendered page. Visual diffs do not contribute to scores. The generated
`analysis.json` and `audit/` files are the source of numerical results and
independent limitations; do not infer a validated style-restoration percentage.
