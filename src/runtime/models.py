"""The one place that names the Codex model each flow uses; change a flow here."""

from __future__ import annotations

# `book prepare`, `book ingest`, `book proofread` and EPUB review judgments.
QUOTE_REVIEW_MODEL = "gpt-6.1-terra"

# Bilingual translation and style transfer; later models only on capacity or outage.
TRANSLATION_MODEL_ORDER = ("gpt-5.6-sol", "gpt-6.1-terra", "gpt-6.1-luna")

# Direct scene-positive translation pass and its review pass.
SCENE_POSITIVE_MODEL = "gpt-5.6-sol"
SCENE_POSITIVE_REVIEW_MODEL = "gpt-6.1-terra"

# Jinjiang genre/time-area classification for dataset export; None uses the Codex default.
CLASSIFIER_MODEL: str | None = None
