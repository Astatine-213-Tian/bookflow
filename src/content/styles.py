"""The shared reading style; Notion layout does not determine line spacing."""

CSS = """
body { font-family: serif; line-height: 1.7; margin: 1em; }
h1 { font-size: 1.6em; text-align: center; margin: 1em 0 0.6em; }
h2 { font-size: 1.3em; text-align: center; margin: 1em 0 0.4em; }
h3 { font-size: 1.1em; margin: 0.8em 0 0.3em; }
p { text-indent: 2em; margin: 0.3em 0; }
.intro p { text-indent: 0; }
aside[role="doc-footnote"] { font-size: 0.9em; margin: 0.7em 0; text-indent: 0; }
a[role="doc-noteref"] { vertical-align: super; font-size: 0.75em; }
.zh-translation { margin-top: 0.2em; margin-bottom: 0.8em; }
"""
