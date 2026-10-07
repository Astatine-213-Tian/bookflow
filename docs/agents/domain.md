# Domain docs

This repository uses a single-context layout:

- `CONTEXT.md`: domain vocabulary and model.
- `docs/adr/`: architectural decision records.

## Reading

Before exploring the codebase, read `CONTEXT.md` and ADRs relevant to the task.
If they do not exist, proceed silently. The domain-modeling skill creates
them when terminology or decisions are resolved.

For implementation architecture and module ownership, also follow
`docs/architecture.md` as directed by `AGENTS.md`.

## Vocabulary and decisions

Use terms defined in `CONTEXT.md` consistently in proposals, issues and code.
Identify genuine vocabulary gaps for domain-modeling.

If a proposal conflicts with an existing ADR, name the ADR and explain why
the decision should be reconsidered.
