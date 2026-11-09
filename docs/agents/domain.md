# Domain docs

Single-context layout: `CONTEXT.md` holds the domain vocabulary and `docs/adr/`
the architectural decision records; shared Notion decisions are the `notion-books`
and CMS ADRs linked from `docs/architecture.md`. The domain-modeling skill creates
missing files when a term or decision is resolved.

- Before exploring the codebase, read `CONTEXT.md` and the ADRs relevant to the
  task; proceed silently when they do not exist.
- Use `CONTEXT.md` terms consistently in proposals, issues and code; report genuine
  vocabulary gaps to domain-modeling.
- When a proposal conflicts with an ADR, name the ADR and explain why the decision
  should be reconsidered.
