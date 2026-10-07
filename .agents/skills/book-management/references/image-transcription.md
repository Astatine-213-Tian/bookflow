# Image Transcription

Use direct Codex vision for supplied text images. Do not use traditional OCR
(such as Tesseract, PaddleOCR, system text recognition or OCR services), even to
prepare a draft or resolve a disagreement. Cropping, rotation and resizing with
ordinary image utilities are allowed; generative reconstruction is not evidence.

## 1. Inventory and Split

List every image in the user's order. Keep a coverage record and transcription
artifacts under `generated/<task>/`; do not commit source images or source text.
Open originals with an image-viewing tool at readable resolution. For tall images,
make overlapping vertical crops with original coordinates and several complete
lines of overlap. Include the very top and bottom; a downscaled whole-image preview
does not establish coverage. Split further whenever text or output would be too long.

## 2. Read Independently in Parallel

For multiple images, always spawn parallel Codex agents. Assign manageable image
or crop batches, queueing more as slots become available. Every source region must
receive two independent visual transcriptions; the primary session may be one
reader. Readers must save their own transcription before seeing another reading.

Give each reader the source paths, exact assigned regions, separate output paths
and fidelity rules below. Save text incrementally per image or crop, with coverage,
uncertain passages and the last completed boundary recorded separately. Return
file paths and status; do not rely on a single long chat response. Resume an
incomplete assignment from its recorded boundary, never treating a truncated or
empty response as evidence of blank source text.

In the raw transcription, preserve wording, punctuation, paragraph breaks, scene
breaks, titles and end markers. Join visual line wraps within paragraphs. Record
source typos and unusual punctuation faithfully; the output formatting pass below
is separate from recognition. Record any excluded
interface text or watermark separately. Flag uncertain readings; do not infer
missing text from context or silently replace it with plausible prose.

## 3. Reconcile Against the Images

Compare both readings at character and paragraph level; scripts may compare text
but must not recognize it. Reopen the original region for every discrepancy or
uncertain passage and record the resolution. Use another independent Codex reader
when needed. Agreement between readers is not proof: visually check every crop
and image boundary for cut lines, missing paragraphs and duplicated overlap.

Assemble in source order. Remove only overlap confirmed against the images;
preserve intentional repetition. Check that every original region has both
readings and that the first and last lines of every image are accounted for.
If text remains illegible, identify the exact region and request a clearer source
or clarification. Keep the draft local until resolved; do not invent a completion.

## 4. Apply Shared Formatting

Keep the reviewed raw transcription unchanged as evidence. Create a separate
output copy and apply [the shared source formatting rules](formatting.md)
before writing any destination. This is mandatory for image sources too, unless
the user explicitly requests a verbatim output. Fix contextually clear quote
direction errors such as `“哦。“` -> `“哦。”` and normalize Chinese/Latin/digit
spacing with the existing normalizer, not a separate image-only implementation.
Review the complete raw-to-formatted diff; retain wording and paragraph boundaries.
Resolve remaining quote findings against neighboring paragraphs and the images.

## 5. Write and Verify

Use the reviewed, formatted copy for the user's requested destination and existing
book-management output workflow. For Notion extras, follow
[fanwai-notion.md](../../../../docs/fanwai-notion.md), including duplicate checks.
Read back the complete written body and compare every paragraph with the formatted
artifact. Verify title, order and any
work relation as well. Matching character counts alone is insufficient.

Complete only when all images and regions are covered twice, discrepancies and
uncertainties are resolved, boundaries and formatting are checked, and the requested
output matches the formatted text. Report the actual destination and any remaining limits
without claiming guaranteed accuracy.
