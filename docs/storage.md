# Local files and cleanup

Paths are relative to the checkout root; run commands from there.

| Location | Holds | Retention |
| --- | --- | --- |
| `book_specs/` | Per-book specs, glossaries, prompts and schemas | In Git. |
| `assets/author_styles/` | Frozen style bundles referenced by specs | Local, outside Git; keep while referenced. |
| Original input location, or `assets/sources/<book>/` | Original images, unique source files, reviewed transcriptions | Keep one authoritative copy; never duplicate originals per task. |
| `state/notion/<source-id>/` | Import identities, write journals, recovery state, covers | Keep after success; future updates and recovery need it. |
| `state/notion/shared-extras/<data-source-id>/comparison.json` | Shared-extra comparison snapshots with observed revisions | Keep across books and resumes (a fresh complete inventory validates reuse); delete to force a full scan. |
| `generated/ingest/`, `generated/updates/` | Working book JSON and preparation/review results | Keep unfinished work and the only reviewed copy; retire intermediates once the destination is verified. |
| `bilingual/<book>/state.json` | Pending run and last successful build | Keep; `book bilingual update` resumes and reuses the baseline from it. |
| `bilingual/<book>/snapshots/<date>/`, `bilingual/<book>/runs/<date>/` | Collected sources, translations, QA evidence | Keep the baseline named in `state.json`, its snapshot and one rollback pair; `book bilingual seed` recovers a lost baseline from the last bilingual EPUB. |
| `books/<author>/` | Final reader outputs | Keep until explicitly replaced or removed. |
| System temporary directory, e.g. `/private/tmp/bookflow-<task>/` | One-off scripts, API probes, screenshots, crops, preview builds | Remove once the task is verified. |
| `/private/tmp/bookflow-codex-backups/` | Archive repair backups | Keep until independent verification shows the installed book is correct. |

`generated/` is a working area, not an archive of agent actions: save there only
what a maintained workflow needs for review, resume or reuse.
`research/datasets/` and `research/generated/` follow the
[research guidelines](../research/AGENTS.md).

## Finishing a task

1. Verify the destination and save any identities or journals recovery needs.
2. Keep unique inputs and reviewed decisions; then remove an EPUB/TXT import's
   temporary inventory, duplicate content copies and diagnostic logs.
3. For translation, validate the replacement baseline before retiring older runs.
   Keep each retained run whole (removing individual requests, reviews or
   translations can invalidate its provenance), and check configuration and test
   references before deleting a historical run.
4. Remove derived crops once originals and reviewed transcriptions are preserved.
   A finished audit keeps a compact result; duplicate request payloads and repeated
   page snapshots are temporary.

Clean up from an explicit file list, re-checked for changes since inspection.
Unfinished work and referenced assets stay; age alone never makes a file
disposable. Delete discarded working trees rather than copying them elsewhere.
