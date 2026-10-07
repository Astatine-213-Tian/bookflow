# Local files and cleanup

Paths below are relative to the checkout. Run maintained commands from its root.

| Location | Purpose | Retention |
| --- | --- | --- |
| `book_specs/` | Maintained configuration, glossaries, prompts and schemas | Version in Git. |
| `assets/author_styles/` | Frozen style bundles referenced by configuration | Keep while referenced; local, outside Git. |
| Original input location, or `assets/sources/<book>/` | Original images, unique source files and reviewed transcriptions | Keep the authoritative copy; avoid duplicating originals per task. |
| `state/notion/<source-id>/` | Import identities, write journals, recovery state and covers | Keep for future updates and recovery, including after successful upload. |
| `generated/ingest/`, `generated/updates/` | Working content JSON and preparation/review results | Keep unfinished work and the only reviewed copy; retire intermediates after destination verification. |
| `generated/crawls/`, `generated/translation_runs/` | Collected sources, translations and QA evidence | Keep the current verified baseline with its matching source and one rollback pair. |
| `books/<author>/` | Final reader outputs | Keep until explicitly replaced or removed. |
| System temporary directory, e.g. `/private/tmp/bookflow-<task>/` | One-off scripts, API probes, screenshots, crops and preview builds | Remove when the task is verified. |

`generated/` is a working area, not an archive of every agent action. Save artifacts
there when a maintained workflow needs them for review, resume or reuse. Brief
inspection results can stay in the session; tests use `TemporaryDirectory`.
Research owns its separate `research/datasets/` and frozen `research/generated/`
evidence under [its guidelines](../research/AGENTS.md).

## Finishing a task

1. Verify the destination and save any identities or journals needed for recovery.
2. Retain unique inputs and reviewed decisions. An EPUB/TXT import's temporary
   inventory, duplicate content copies and diagnostic logs can then be removed.
3. For translation, validate the replacement baseline before retiring older runs.
   Keep each retained run's complete provenance-bound files: removing individual
   requests, reviews or translations can invalidate it. Check configuration and
   test references before deleting a historical run.
4. Remove derived crops when originals and reviewed transcriptions are preserved.
   For completed audits, a compact result is usually sufficient; duplicate request
   payloads and repeated page snapshots are temporary.

Cleanup uses an explicit file list and checks for changes since inspection. It
preserves unfinished work and referenced assets; age alone does not prove a file
is disposable. Do not copy discarded working trees elsewhere indefinitely.
Archive repair backups use `/private/tmp/bookflow-codex-backups/` until independent
verification establishes that the installed book is correct.
