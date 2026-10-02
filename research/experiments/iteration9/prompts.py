from __future__ import annotations

from experiments.iteration5.pilot import STRING, STRINGS, object_schema
from experiments.iteration6.prompts import ALIGN, ALIGN_SCHEMA, BOOL, SOURCE_JUDGE, SOURCE_SCHEMA

INDEX = {"type": "integer", "minimum": 0}
PATCH = object_schema({"paragraph_index": INDEX, "before": STRING, "after": STRING,
                       "reason": STRING})
EDIT_SCHEMA = object_schema({"patches": {"type": "array", "items": PATCH}, "notes": STRINGS})
ALIGN_PRECISE = ALIGN + """
Also return first_paragraph_quote and last_paragraph_quote as EXACT contiguous text from
the selected first/last Chinese lines, preserving punctuation and spacing. These quotes
define the boundary crops for the reader: include only the corresponding passage, not
unrelated lead-in/continuation. A boundary may lie inside a paragraph or sentence.
For a multi-line selection the first quote must be a suffix of start_line and the last a
prefix of end_line; all nonblank lines between are kept verbatim. If the selection lies
in one line, return the SAME exact relevant substring in both fields. Do not translate
English-only content into Chinese. Do not drop a corresponding author expression merely
because the English words differ. Record unavoidable edition differences separately.
"""
ALIGN_PRECISE_SCHEMA = object_schema({**ALIGN_SCHEMA["properties"],
                                     "first_paragraph_quote": STRING, "last_paragraph_quote": STRING})

EDIT = """Edit a Chinese novel scene toward the demonstrated author's way of telling it.
You see a shared Chinese draft and cross-book diagnostic cards, NOT the target English or
the target author's Chinese answer. Cards are conditional style preferences, not proven
grammar corrections or instructions to imitate their plot, names, vocabulary or wording.
Their English/author anchors explain boundaries; never import their details into the target.

Read the whole scene for voice and timing. Even an acceptable, grammatical sentence MAY be
locally reorganized if the demonstrated preference fits: combine a supporting posture or
simultaneous movement with the main action; let a concrete predicate carry an expression
instead of wrapping it in an abstract description; preserve conversational dialogue and
lightly tossed-off narrator commentary; place a comic judgment where the sentence lands.
Use ordinary idiomatic Chinese. Do not replace a compact but slightly awkward phrase with
a long schoolbook explanation merely to make its grammar more explicit.

Preserve all draft content: actors, gestures, actions, causal/temporal relationships,
direction and viewpoint, intentions, uncertainty, degree, meaningful manner, speech turns,
comedic delay and purposeful repetition. Two related states need not be two explanations,
but neither state may disappear. Preserve terms/names/numbers exactly; terminology work is
outside this experiment. Do not infer extra physical movements or correct alleged facts
from Chinese context alone. Do not soften explicit intensity simply to sound casual.
Conversely, stylistic naturalness does not require a separate Chinese word for every idea
when one construction expresses the same meaning. Keep necessary English-inherited detail
present in the draft, even if a shorter author anchor in a training card omitted it.

This is not a mandate for shorter text, fewer sentences, comma chains, ban lists, colloquial
particles everywhere, or generic literary polishing. A quiet pause or formal register can
be exactly right for a particular speaker/scene. Leave successful passages unchanged.
The boundary-only card is NOT an instruction to make its proposed non-edit; the keep card
demonstrates when to stop. Optional scene-specific cards have limited scope. No edit quota.

Return only local paragraph patches, indexed zero-based into supplied paragraphs. Each
before must occur EXACTLY ONCE in that paragraph. Patches must not overlap; all before spans
refer to the ORIGINAL draft, not earlier patches. After replaces only that span. Patches
may reorganize clauses inside a paragraph but cannot delete or merge paragraphs, rename
terms, add facts, or rewrite the entire scene. Use a whole-paragraph span only when needed
for a local clause reordering. If no justified improvement exists, return an empty list.
Explain the applicable operation briefly. JSON only.
"""

QA = """Independently check a Chinese translation against its English target and context.
You do NOT see the editor's explanations, training cards, other candidate or author Chinese.
Check all paragraphs for demonstrable semantic defects: missing/added facts, actors,
direction, time, causation, negation, uncertainty, degree or speaker attribution.
Chinese may combine simultaneous actions, reorder clauses, change punctuation, replace
literal words with an idiomatic construction, or leave recoverable arguments implicit.
Do not demand English-shaped syntax or a separate surface word for every source idea.
An idiomatic construction that carries the same source meaning is faithful. Do not make
style-preference edits, normalize names, simplify justified repetition, or restore literal
phrases just because you recognize their English counterpart. Intensity and relationships
actually stated in English still matter. If a translation is arguable but faithful, keep it.

Return minimal exact-substring repair proposals ONLY when there is a concrete source-backed
meaning defect. Each English support quote must be exact and contiguous from target/context.
paragraph_index is zero-based; before occurs exactly once in that Chinese paragraph, and
all proposed spans refer to the original supplied Chinese and must not overlap. No full
scene regeneration. Empty patches is valid. JSON only.
"""
QA_PATCH = object_schema({**PATCH["properties"], "english_support": STRING,
                          "severity": {"type": "string", "enum": ["minor", "major"]}})
QA_SCHEMA = object_schema({"patches": {"type": "array", "items": QA_PATCH}, "notes": STRINGS})
VERIFY_QA = """Review each proposed English-fidelity repair independently. You have English
and Chinese but NO editor rationale, training cards or author Chinese. Accept only when
before has a demonstrable meaning defect and after repairs it while preserving the rest.
Chinese idiom, implicit recoverable arguments, combined actions, reordered clauses, and
different punctuation do not require literal word-for-word restoration. Reject a proposal
that merely changes register, strengthens/weakens a defensible expression, or reverts a
faithful compact construction to an English-shaped explanation. Do not invent new edits
or alternative wording. Output one decision for EVERY proposal_index, with a brief reason.
"""
VERIFY_SCHEMA = object_schema({"decisions": {"type": "array", "items": object_schema({
    "proposal_index": INDEX, "accept": BOOL, "reason": STRING})}})

FINAL_AUDIT = SOURCE_JUDGE + """
This is a frozen reading experiment. Do not pick a preferred method or provide an overall
score. Ignore terminology spelling differences; distinguish a spelling variant from a true
actor/fact change. Preserve source-explicit intensity and content even when a plain Chinese
alternative sounds lighter. Citation spans must be verbatim. Report possible concerns;
these are model findings for review, not automatic proven errors or permission to rewrite.
"""
