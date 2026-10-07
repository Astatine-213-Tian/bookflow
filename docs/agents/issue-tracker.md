# Issue tracker: GitHub

Issues and specs live in GitHub Issues for
`Astatine-213-Tian/bookflow`. Use the `gh` CLI from this clone.

## Operations

- Create: `gh issue create --title "..." --body-file <file>`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,body,labels`
- Comment: `gh issue comment <number> --body-file <file>`
- Label: `gh issue edit <number> --add-label <label>` or `--remove-label <label>`
- Close: `gh issue close <number>`

Write multiline bodies to a file and pass `--body-file`.
Use pagination or appropriate limits when complete enumeration is required.

“Publish to the issue tracker” means create a GitHub issue.
“Fetch the relevant ticket” means read the issue and its comments.

## Pull requests as a triage surface

PRs as a request surface: no.

## Wayfinding

- Keep the map in one issue labelled `wayfinder:map`.
- Create child tickets as sub-issues. If unavailable, use a task list in the
  map and a `Part of #<map>` reference in each child.
- Label children `wayfinder:<type>`, where type is research, prototype,
  grilling, or task.
- Record blockers using native issue dependencies. If unavailable, use a
  `Blocked by: #<number>` line in the child.
- Select open, unassigned children whose blockers are closed, in map order.
- Claim a ticket by assigning it to the driving developer before starting.
- Resolve by recording the result, closing the ticket, and adding a summary
  and link to the map's Decisions-so-far.
