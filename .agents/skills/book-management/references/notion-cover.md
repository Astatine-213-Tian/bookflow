# Native Notion cover upload

For a pending `cover-browser.json` or a browser upload the user requests.
`src/notion/cover.py` owns validation, API upload and byte-for-byte
verification; code-only changes and fixture tests need no live browser. The task
is written only when no Notion REST token is configured; with the token,
`book notion resume --state …` uploads and verifies the cover through the API.

1. Read the task's work URL, asset, SHA-256 and import checkpoint. Check the asset
   with `validate_cover` and confirm its bytes still match the checkpoint. Retry on
   the existing work page; never create another book for a cover.
2. Read the installed `browser-harness` skill. Use the user's authenticated Arc
   session through a compatible adapter listed by `arc-cdp adapters`
   (`arc-cdp run <adapter> ...`), in a full-window tab, preserving the session;
   a test Chrome profile lacks the user's Notion login.
3. Inspect the work page's current cover; replace a different cover only within
   the user's requested scope. Open the cover upload panel and locate the actual
   DOM `input[type=file]`.
4. Assign the absolute asset path to that input with the adapter's documented
   file-input method (read its documentation first) rather than the native macOS
   chooser. If the adapter supplies no file bytes, inspect the input, the browser
   error or the harness capability instead of clicking Upload/Open again.
5. Wait for the upload, close the panel, reload and inspect the visible cover, then:

   ```bash
   uv run book notion verify-cover --state state/notion/RUN/import.json
   uv run book notion resume --state state/notion/RUN/import.json
   uv run book notion verify --state state/notion/RUN/import.json
   ```

Done when `verify-cover` passes: it downloads the current native cover through
REST, checks the prepared SHA-256 and only then marks it uploaded, also resolving
an uncertain API attachment. A click, chooser screenshot or spinner is not proof.
Leave `cover_uploaded` to `verify-cover`, and keep signed URLs, browser
credentials and tokens out of source and evidence files.
