# Live Notion upload test

`tests/live_notion_upload.py` injects a synthetic `CrawledBook` at the collection
boundary, then runs the real source preparation, metadata mapping, duplicate
scan, template application, chapter/extra upload, checkpoint persistence, resume
and full readback. Provider parsing is covered by fixtures, not here. It passes
when the uploaded content matches the prepared source and resume preserves page
identities. It never publishes; the synthetic book has no cover, so native cover
upload needs its separate test.

Prerequisites: the ordinary unit tests pass; the user has authorized creating and
cleaning up live test pages; `book notion login` is done and the REST integration
can access the databases in `book_specs/notion/config.json`, whose database and
template must already exist.

```bash
live_state=$(mktemp -d /private/tmp/crawler-notion-live.XXXXXX)
uv run python tests/live_notion_upload.py import --state "$live_state"
```

Keep `live_state` to diagnose a failure; never retry an ambiguous creation by
discarding its checkpoint. Unset unsupported machine-wide SOCKS proxy settings
for the command if they break it.

After success or failure, move only the test work (including its chapter
database), author and created extra listed in `run.json` and its `import_state`
to Notion Trash, through the Notion UI or a REST page update (`in_trash: true`).
If a create response was lost, find the pages by the unique `marker` in their
names. Then check the active inventories:

```bash
uv run python tests/live_notion_upload.py verify-cleanup --state "$live_state"
```

Keep any useful report, then delete the isolated test state.
