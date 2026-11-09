# Image Transcription

Read supplied text images with Codex vision. Ordinary image utilities may crop,
rotate and resize; traditional OCR (Tesseract, PaddleOCR, system text
recognition, OCR services) and generative reconstruction are never evidence, not
even for a draft or a disagreement.

## 1. Inventory and Split

List every image in the user's order. Crops and comparison drafts go in a system
temporary task directory; keep originals, reviewed transcriptions and the
coverage record per [storage](../../../../docs/storage.md). View originals at
readable resolution. Cut tall images into overlapping vertical crops, recording
original coordinates, with several complete lines of overlap and the very top and
bottom included; a downscaled whole-image preview does not establish coverage.
Split further whenever text or output would be too long.

## 2. Read Independently in Parallel

For multiple images, spawn parallel Codex agents on small image or crop batches,
queueing more as slots free. Every region gets two independent transcriptions;
the primary session may be one reader. Each reader saves its transcription
before seeing another reading.

Give each reader the source paths, exact regions, its own output paths and the
fidelity rules below. Readers save text incrementally per image or crop, record
coverage, uncertain passages and the last completed boundary separately, and
return file paths and status rather than one long chat response. Resume an
incomplete assignment from its recorded boundary; a truncated or empty response
never means blank source text.

Fidelity rules for the raw transcription: preserve wording, punctuation,
paragraph and scene breaks, titles and end markers, and join visual line wraps
within paragraphs. Record source typos and unusual punctuation as they are, and
excluded interface text or watermarks separately. Flag uncertain readings rather
than inferring missing text from context.

## 3. Reconcile Against the Images

Compare both readings at character and paragraph level; scripts may compare text
but never recognize it. Reopen the original region for every discrepancy or
uncertain passage, record the resolution, and add another independent reader when
needed. Agreement is not proof: visually check every crop and image boundary for
cut lines, missing paragraphs and duplicated overlap.

Assemble in source order, removing only overlap confirmed against the images and
preserving intentional repetition. Every region must have both readings and the
first and last lines of every image must be accounted for. For illegible text,
name the exact region and ask for a clearer source or clarification; the draft
stays local until resolved.

## 4. Apply Shared Formatting

Keep the reviewed raw transcription unchanged as evidence. Unless the user asks
for verbatim output, apply the [shared formatting rules](../../../../NORMALIZATION.md)
to a separate output copy before writing any destination, using the existing
normalizer: fix contextually clear quote direction such as `“哦。“` -> `“哦。”`
and Chinese/Latin/digit spacing. Review the complete raw-to-formatted diff for
unchanged wording and paragraph boundaries, and resolve remaining quote findings
against neighbouring paragraphs and the images.

## 5. Write and Verify

Write the formatted copy through the book-management output workflow; Notion
extras follow [shared extras](../../../../docs/fanwai-notion.md), including its
duplicate check. Read back the complete written body and compare every paragraph
with the formatted copy, plus title, order and any work relation; matching
character counts alone prove nothing.

Done when every image and region is covered twice, discrepancies and
uncertainties are resolved, boundaries and formatting are checked, and the output
matches the formatted copy. Report the actual destination and any remaining
limits without claiming guaranteed accuracy.
