# Issue tracker: GitHub

Issues and specs live in GitHub Issues for `Astatine-213-Tian/bookflow`; use
`gh issue` from this clone. “Publish to the issue tracker” means create an issue;
“fetch the relevant ticket” means `gh issue view <number> --comments`. Pass
multiline bodies with `--body-file`, and paginate or raise `--limit` when every
issue is needed. Pull requests are not a request surface.

## Wayfinding

- Keep the map in one issue labelled `wayfinder:map`.
- Create child tickets as sub-issues; if unavailable, use a task list in the map
  and a `Part of #<map>` line in each child.
- Label children `wayfinder:<type>`: research, prototype, grilling or task.
- Record blockers as native issue dependencies; if unavailable, add a
  `Blocked by: #<number>` line to the child.
- Select open, unassigned children whose blockers are closed, in map order, and
  claim one by assigning it to the driving developer before starting.
- Resolve by recording the result, closing the ticket, and adding a summary and
  link to the map's Decisions-so-far.
