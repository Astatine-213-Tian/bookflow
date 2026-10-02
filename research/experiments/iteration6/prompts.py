from __future__ import annotations

from experiments.iteration5.pilot import DIRECT, STRING, STRINGS, TEXT_SCHEMA, object_schema

INT = {"type": "integer"}
BOOL = {"type": "boolean"}

ALIGN = """Find the exact author-Chinese paragraphs corresponding to the supplied English
window in the numbered Chinese search region. Return existing line indices only; never
invent or rewrite author text. The smallest contiguous span covering the English window
is preferred, but note boundary mismatches and missing/extra meaning. An English paragraph
may correspond to several Chinese lines, and vice versa. If uncertain, mark aligned=false.
Record English/Chinese edition differences separately, with exact visible quotations.
Do not evaluate any model translation. Do not produce style examples or a glossary.
scene_kind describes narrative function (dialogue, action, exposition, quiet emotion, mixed).
Return JSON only."""
DIFF = object_schema({"english_quote": STRING, "chinese_quote": STRING, "difference": STRING})
ALIGN_SCHEMA = object_schema({"aligned": BOOL, "start_line": INT, "end_line": INT,
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "scene_kind": STRING, "boundary_notes": STRINGS,
    "edition_differences": {"type": "array", "items": DIFF}})

MINE = """Review a directly generated Chinese translation against its English source,
using actual author-Chinese as expression evidence. Identify only CLEAR wording problems:
unidiomatic collocations/complements, English-shaped clause construction, avoidable empty
framing, duplicate expression of the SAME meaning, or an unjustified register. Do not
manufacture errors to fill a quota. An acceptable alternative is not an error merely
because the author chose differently. Long sentences, comic repetition and informative
modifiers are not errors. Distinguish wording from semantic mistakes and edition differences.
For each candidate give exact contiguous before text from the draft, a minimal after repair
that preserves ALL explicit English meaning, exact English support and exact author anchor.
Never delete an English addition to imitate a shorter Chinese original. A wording edit can
coexist with a nearby edition difference. Reject target phrases contaminated by that
difference; retain unaffected phrases. Record preferences, meaning mistakes, uncertainty
and edition differences separately as excluded observations. There is no minimum number.
Only JSON."""
EXAMPLE = object_schema({"before": STRING, "after": STRING, "english_support": STRING,
    "author_anchor": STRING, "category": STRING, "reason": STRING})
MINE_SCHEMA = object_schema({"proposals": {"type": "array", "items": EXAMPLE},
    "excluded_observations": STRINGS})

VERIFY = """Independently audit proposed wording examples. Be strict: is the before
actually unnatural/cumbersome, rather than merely a legitimate alternative? Does the
minimal after preserve every fact, uncertainty, degree, speaker and perspective explicitly
in English? The author original is stylistic evidence, NOT the semantic authority. Reject
omissions of English-added meaning, fact repairs mislabeled as style, debatable preferences,
and unnecessary literary polishing. Accept only a clear wording problem with an equally
faithful, more idiomatic repair. Do not rewrite proposals or add new ones. Give a reason
for each ID; no quota. Only JSON."""
VERIFY_SCHEMA = object_schema({"decisions": {"type": "array", "items": object_schema({
    "example_id": STRING, "accept": BOOL, "reason": STRING})}})

POSITIVE = """\nwording_examples are independently checked, minimally corrected translations
from TRAIN books, not verbatim author originals. Learn the Chinese construction from
these additional positive examples, without borrowing their facts or particular phrases.
Each corrected_chinese_fragment is only a LOCAL phrase within english_context, NOT a
complete translation of that English context. Unrepresented contextual information is
not permission to omit meaning from your new scene. Do not shorten for its own sake;
preserve all source information and meaningful repetition."""
CONTRAST = POSITIVE + """\nEach wording_example also includes a rejected before and a specific
reason for the edit. Apply that editing decision when the same construction is genuinely
awkward in the new scene. Do not mechanically replace vocabulary or impose a length target.
Avoid empty framing and duplicated explanation while keeping content-bearing detail."""

EDIT = """Edit the supplied Chinese novel scene for clear idiomatic wording problems.
You do not have its English or author-original answer. The training contrasts demonstrate
minimal repairs of awkward verb constructions, cumbersome framing and duplicate expression.
Preserve all information already in the draft: actions, modifiers, intensity, uncertainty,
relationships, point of view, dialogue turns, comic pauses and purposeful repetition.
Do not summarize, add literary color, infer new gestures/emotions, or aim at a shorter length.
An already natural sentence should stay unchanged. Return the entire scene in paragraphs,
with notes explaining the specific repairs. JSON only."""
QA = """Check the edited Chinese scene against English. Repair ONLY demonstrable semantic
errors: missing or added facts, degree, negation, timing, actors, viewpoint, or dialogue.
Keep the edited Chinese wording wherever faithful; do not revert it to English syntax.
Do not rewrite for preference, copy training prose, or use any author-original answer.
Return full paragraphs and precise notes identifying actual fixes; JSON only."""

SOURCE_JUDGE = """Independently review anonymous Chinese translations of one English scene.
You have NO author-original answer. For every candidate mark concrete, distinct clear wording
errors (unnatural idiom/collocation, cumbersome empty framing, duplicate same-meaning clauses,
or unjustified register) separately from English fidelity errors. A valid alternative, long
sentence, purposeful repetition, or faithfully translated English verbosity is NOT a wording
error. Cite an exact candidate span for every error and explain a minimal repair. For fidelity
cite an exact source span and classify major/minor; do not count the same defect twice as
wording and meaning. No numerical overall quality score. Zero is allowed; do not fill quotas.
Return an assessment for every opaque candidate ID. JSON only."""
ISSUE = object_schema({"quote": STRING, "source_quote": STRING, "reason": STRING,
    "repair": STRING, "severity": {"type": "string", "enum": ["major", "minor"]}})
SOURCE_SCHEMA = object_schema({"assessments": {"type": "array", "items": object_schema({
    "candidate_id": STRING, "wording_errors": {"type": "array", "items": ISSUE},
    "meaning_errors": {"type": "array", "items": ISSUE}, "notes": STRINGS})}})

STYLE_JUDGE = """Compare anonymous translations with actual author-Chinese for a scene.
Rank resemblance of phrasing, clause rhythm, narrator distance, dialogue and comic/emotional
beats, allowing ties. Do not reward brevity, word overlap or ornate language as style.
English is each candidate's semantic authority: ignore author effects/meaning absent from
English and do not penalize faithful English-added content. The frozen edition ledger may
be incomplete: explicitly record further inherited differences instead of blaming candidates.
Give exact candidate quotes supporting each judgment; identify avoidable English-shaped
wording versus acceptable stylistic alternatives. Do not infer method identity. These are
exploratory model preferences, not reader results or author-recovery percentages. JSON only."""
STYLE_SCHEMA = object_schema({"ranking": {"type": "array", "items": STRINGS},
    "evidence": {"type": "array", "items": object_schema({"candidate_id": STRING,
        "quote": STRING, "assessment": STRING})}, "limitations": STRINGS})
