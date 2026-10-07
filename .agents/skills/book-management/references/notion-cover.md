# Native Notion cover upload

Use this procedure for a pending native cover in `cover-browser.json`, or when
the user requests a browser upload. `src/notion/cover.py` owns cover validation,
API upload and byte-for-byte verification. No live browser action is necessary
for a code-only refactor or fixture test.

1. Read the task's work URL, local asset, SHA-256 and import checkpoint. Validate
   the asset with `validate_cover`; confirm its bytes still match the checkpoint.
   Use the existing work page. Never create another book to retry a cover.
2. Read the installed `browser-harness` skill. For the user's authenticated Arc
   session, run `arc-cdp adapters` and select a listed compatible adapter through
   `arc-cdp run <adapter> ...`. Keep a full-window tab and preserve the session.
   Do not attach a test Chrome profile expecting the user's Notion login.
3. Inspect the exact work page and its current cover. If a different cover exists,
   resolve against the user's requested replacement scope before overwriting it.
   Open the cover upload panel and locate the actual DOM `input[type=file]`.
4. Use the selected adapter's documented file-upload/file-input method with the
   absolute asset path. Read that method's installed documentation before use.
   Prefer assigning the file to the DOM input over invoking the native macOS
   chooser. Do not repeatedly click Upload/Open when the adapter never supplies
   file bytes; inspect the input, browser error or harness capability instead.
5. Wait for upload completion, close the panel and reload the page. Inspect the
   visible cover and run the independent readback:

   ```bash
   uv run book-notion verify-cover --state generated/notion_cms_sources/RUN/import.json
   uv run book-notion resume --state generated/notion_cms_sources/RUN/import.json
   uv run book-notion verify --state generated/notion_cms_sources/RUN/import.json
   ```

`verify-cover` fetches current native-cover metadata and its bytes, checks the
prepared SHA-256, and only then marks it uploaded. It also resolves an uncertain
API attachment after the same verification. A click, chooser screenshot or upload
spinner is not proof. Do not set `cover_uploaded` manually or persist signed URLs,
browser credentials or tokens in source/evidence files.
