# Author Style Research Index

This directory is the maintained written record for the Eternal Gate
author-style research. Start with the research plan, then read the numbered
reports in order. Generated JSON, model outputs, and private benchmark packets
remain under `../generated/`; reports contain the human-readable procedure,
results, limitations, and independent evaluations.

## Current Decision

The production pipeline uses `content_plan_combined_full_regeneration` because it
showed the strongest relative behavior among the retained prompt methods and was
preferred in direct Eternal Gate review. Iteration 4 did not pass its formal
academic gate, so this remains an engineering choice rather than a claim of
validated transfer efficacy.

The September real-bilingual scene pilot favors direct scene reconstruction
over Method4 on average, with one non-winning scene and fidelity caveats. This
is exploratory evidence only; it does not change the production decision.

The subsequent seeded wording-bank probe found only one strict correction in
12 training windows. On six fresh development windows, independent blind close
reading found no consistent gain over direct translation; local editing tied it
throughout. Clear-error mining and author-style preference data need distinct labels.

Iteration 8 uses 48 passages across six books, eight per book, with volume
and chapter stratification. It supersedes the earlier two-book 50-passage allocation;
old samples and feedback remain archived. Human feedback, rather than sample count,
is needed to compare the methods.

The first partial feedback snapshot favors local editing (8 single preferences),
followed by direct and positive-example translation (6 each), then contrastive
examples (1). [Source-grounded style diagnostics](../experiments/validation/style_feedback/README.md)
compare all 48 passages and curate local differences; this is post-hoc diagnostic
work, not a new transfer iteration or a production-method promotion.

The [Iteration 9 paired reader](../experiments/iteration9/README.md)
contains 48 fresh scenes, six books with eight scenes each, comparing the old
local-editing pipeline and a new structural-patch/semantic-QA package from the
same direct drafts. The first 12 are a balanced reading checkpoint. Generation,
independent provenance/source-boundary review and reader testing are complete.
The user subsequently expressed dissatisfaction with both variants; remaining
fidelity concerns also prevent claiming that the new pipeline is better.

The current [Iteration 10 reader](../experiments/iteration10/README.md) returns
to the unchanged direct and positive-example methods, each previously selected
six times. It contains 48 fresh paired scenes, eight per book, generated directly
without subsequent editing. New human comparison will determine preference;
earlier votes remain separate archives.

## Research Plan

- [Research plan](research_plan.md): questions, data roles, leakage controls,
  evaluation design, advancement gates, and production handoff rules.

## Reports

| Order | Report | Main result |
| ---: | --- | --- |
| 1 | [Dataset curation and masking](reports/01_dataset_curation_and_masking.md) | 50-author corpus, strict book-level splits, train-fitted global masking, and a book-local diagnostic view |
| 2 | [Authorship style meter](reports/02_authorship_style_meter.md) | mask-stripped character 2-4 gram TF-IDF plus unweighted SGD hinge; 89.8% test accuracy and 87.9% balanced accuracy |
| 3 | [Transfer Iteration 1](reports/03_transfer_iteration1_prompt_methods.md) | generic cards, retrieval, and close-reading prompt families; NO-GO |
| 4 | [Transfer Iteration 2](reports/04_transfer_iteration2_aligned_pairs.md) | aligned neutral-to-author pairs; NO-GO |
| 5 | [Transfer Iteration 3](reports/05_transfer_iteration3_constrained_rerank.md) | constrained edits, microcards, and reranking; NO-GO |
| 6 | [Transfer Iteration 4](reports/06_transfer_iteration4_full_regeneration.md) | full regeneration and content-plan methods; formal development NO-GO |
| 7 | [Transfer Iteration 5](reports/07_transfer_iteration5_real_parallel_scene_pilot.md) | real parallel examples and scene reconstruction; direct route promising on four scenes, no production promotion |
| 8 | [Transfer Iteration 6](reports/08_transfer_iteration6_sampled_wording_bank.md) | strict wording bank sparse; four-arm fresh probe shows no consistent improvement over direct translation |
| 9 | [Transfer Iteration 7](reports/09_transfer_iteration7_expanded_reading.md) | 50 fresh passages, four-column source-visible reader, persistent human feedback; no quality conclusion yet |
| 10 | [Transfer Iteration 8](reports/10_transfer_iteration8_balanced_reading.md) | Main reading task reallocated to 48 groups across six books, eight per book; old feedback archived |
| 11 | [Transfer Iteration 9](reports/11_transfer_iteration9_paired_structural_editing.md) | 48 same-draft editing pairs completed; the user subsequently disliked both variants; semantic limitations recorded |
| 12 | [Transfer Iteration 10](reports/12_transfer_iteration10_direct_positive_reading.md) | 48 fresh direct/positive pairs using the original methods, with no later editing; ready for new human comparison |

Each transfer iteration has exactly one canonical report. Earlier drafts and the
abandoned single-author profile are not part of this report sequence.

Post-transfer meter and application diagnostics are documented with their code
under [`../experiments/validation/`](../experiments/validation/README.md). They
are supporting evidence, not additional transfer iterations. The meter and
application diagnostics predate the real-bilingual Iteration 5; the feedback
diagnostics analyze the subsequent Iteration 8 reading study.

## Literature Notes

- [01: Chinese stylometry](literature/01_stylometry_chinese_author_profile.md)
- [02: Corpus stylistics and evidence cards](literature/02_corpus_stylistics_evidence_cards.md)
- [03: Back-translation and style transfer](literature/03_textless_back_translation_and_style_transfer.md)
- [04: Retrieval and evaluation](literature/04_retrieval_and_evaluation.md)
- [05: Historical single-author profile methodology](literature/05_author_profile_methodology.md)
- [06: Authorship benchmarks and LLM methods](literature/06_author_style_benchmark_and_llm_methods.md)
- [07: Content masking and content control](literature/07_content_masking_and_content_control.md)

## Reproduction

Commands in the reports assume the current working directory is `research/`:

```bash
cd research
uv sync
make benchmark-authorship
```

`make benchmark-authorship` first rebuilds every clean and masked view from
`datasets/raw/`, then runs the canonical classifier configuration and report. The
classifier rejects chunks that do not carry the current punctuation-normalization
version, so an older generated corpus cannot be used accidentally.

Use [the project README](../README.md) for the short workflow,
[`workflows/README.md`](../workflows/README.md) for maintained commands, and
[`experiments/README.md`](../experiments/README.md) for the numbered experiment map.
