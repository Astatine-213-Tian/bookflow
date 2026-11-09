# Repository Guidelines

bookflow turns sites, files and images into one book JSON and writes EPUB, TXT or
Notion drafts. Every task is a subcommand of one `book` command (`uv run book`
lists them). Each ends with one JSON result line on stdout, logs going to stderr:
act on that line's `status` (`src/cli/output.py`), not on the log text.

- **Book tasks** (add, find, update, repair, proofread, covers, training export,
  crawler providers): use the [book-management skill](.agents/skills/book-management/SKILL.md);
  bilingual books follow the section below.
- **Text images**: transcribe with Codex vision only, never traditional OCR, not
  even for a draft or fallback; follow [image transcription](.agents/skills/book-management/references/image-transcription.md).
- **Code changes**: first read [docs/architecture.md](docs/architecture.md)
  (module ownership, conventions, normalization rule changes, verification).
- **Saving or cleaning up files**: [docs/storage.md](docs/storage.md). One-off
  scripts, probes, crops and previews go in the system temporary directory.
- **Setup**: [dependency installation](docs/notion-books.md#install-shared-dependencies); later
  syncs use `mise exec -- uv sync --locked`.
- **Issues**: [tracker](docs/agents/issue-tracker.md) and
  [triage labels](docs/agents/triage-labels.md); domain terms and decisions:
  [domain docs](docs/agents/domain.md).

Keep credentials, checkpoints, browser profiles, book data and working runs local
and out of Git. Keep documentation, dependency upgrades and verification within
this repository: a task ends at its verified output (local EPUB/TXT, or a Notion
draft read back); publication and deployment belong to other projects.

Commits use Conventional Commits, e.g. `fix(xfxs): repair preview metadata`. A PR
names the target site, validation commands, output path and manual steps such as
Cloudflare verification.

## Bilingual Books

A bilingual book is one spec, `book_specs/<book>/config.json`: `source`,
`translation.method` and glossary, `output`, and `edition` (reviewed identifier,
intro, section titles and extras that every build applies). Record such decisions
in `edition`, never only in a built EPUB. For “update <book>”, e.g. “update eternal
gate” / “更新永恒之门” (`eternal_gate`), run:

```bash
uv run book bilingual update eternal_gate --headless
```

It collects a dated snapshot, reuses the last successful build as baseline,
translates with the spec's method, validates, writes the spec's output and records
the new baseline in `bilingual/<book>/state.json`. Rerunning resumes the pending
run. With no baseline but an earlier bilingual EPUB, first run
`uv run book bilingual seed <book> --from-epub PATH`; `update` then translates only
chapters whose English changed. Act on `status`:

- `complete`: report `outputs` and any `epub_check` issues. Review
  `comment_evidence` against the glossary, preserving canonical names and protected
  quotations; after a reviewed glossary edit, run `update` again. Spot-check
  metadata and scan for placeholder text. TXT is a separate request.
- `review_required`: write the decisions `review` asks for under `review.path`,
  then run the result's `resume` command.
- `failed`: read `error`. After a glossary change on a pending run, rerun with
  `--restart`; for a bad snapshot, `--recrawl`. For a collection failure, inspect
  the actual crawler error first; use Agent Browser or other interactive browser
  tools only for login, verification or inspection, and a verified
  `arc-cdp run <adapter>` for the user's existing Arc session.

A paragraph still empty after the run's retries (neutral methods) stays
English-only, never placeholder or refusal text: run `book bilingual validate` and
`build` with `--allow-missing`, then scan the final EPUB for placeholder strings and
confirm only those paragraphs are English-only.
