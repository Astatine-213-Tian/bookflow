from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from experiments.iteration5.pilot import object_schema, STRING, STRINGS
from experiments.iteration6.probe import binding, run_jobs
from experiments.iteration7.runtime import RESEARCH, REPO, invoke, read, write, sha
from experiments.iteration8 import reader, study

ROOT = RESEARCH / "generated/style_feedback_review_20260927"
SEED = 2026092701
DIMENSIONS = ("action_clause_organization", "narrator_register", "dialogue_rhythm", "explanatory_restraint")
SCORE = {"type": "integer", "minimum": 1, "maximum": 5}
LABELS = {"direct": "直接译写", "positive": "直接译写＋正例", "contrastive": "直接译写＋纠错对照", "edited": "中文局部编辑＋英文核查"}
PROMPT = """Evaluate Chinese novel translations against actual author Chinese, focusing on
recoverable author-style resemblance, not exact wording, terminology, accuracy percentages,
or shorter-is-better. English target and context define the content the translations must preserve.
Author Chinese may add/drop/reorder meaning relative to the published English. Do NOT reward
copying author details absent from English, or deleting meaning explicit in English.
You see anonymous unique candidate texts, no method labels and NO human preferences.

Read the WHOLE scene first, then select 2–4 key local contrast units that explain the main
recoverable stylistic differences. Compare the same semantic/action unit across ALL candidates.
Give EXACT contiguous quotes from the supplied author, English (target or context), and each
candidate. No ellipses, normalized punctuation, stitched phrases, or invented quotes. If no exact
counterpart exists use empty quote, mark unevaluable/uncertain, and do not fabricate a match.
Classify each unit as comparable_style, terminology_only, edition_content_difference, or uncertain.
If an English/Chinese content difference contaminates only part of a unit, choose a smaller
comparable span or exclude the unit. Person/place/species/item name spellings and transliterations
are terminology only and do NOT lower style scores. A true actor/action/fact change is a separate
semantic concern, NOT a terminology penalty or a style preference. Unclear mappings remain uncertain.

For comparable units consider: (1) packing simultaneous/supporting actions into a clause versus
unnecessarily spelling out each movement, (2) extra explanation of inferable intent/emotion,
(3) casual, lightly tossed-off narration versus solemn/clinical/heavy idiom, (4) dialogue timing,
(5) clause/paragraph rhythm and narrator distance. These are preferences, not grammar errors.
Do not call two ordinary synonyms a defect by themselves. Longer language that carries English
facts, useful modifiers, purposeful repetition, comic delay, or author-typical cadence is NOT padding.
Do not reward author-word overlap, shared names, raw edit distance, length compression, or ornate prose.
Any stylistic improvement must still be English-faithful. Distinguish English-inherited heaviness from
avoidable choices in Chinese; do not force author resemblance that English cannot support.

Score each candidate 1–5 on four equally weighted qualitative dimensions:
action_clause_organization, narrator_register, dialogue_rhythm, explanatory_restraint.
Anchors: 1=strong recurring divergence on comparable features; 2=multiple salient divergences;
3=mixed, recognizable similarity with meaningful drift; 4=mostly close with limited local drift;
5=consistently close on available comparable features. These are exploratory ordinal judgments,
NOT validated style-recovery percentages. Mark a dimension in not_assessable_dimensions if the
scene provides no evidence (e.g. no dialogue); its numeric score is a required placeholder ignored
by analysis. Give an overall ranking in tiers, allowing ties generously when differences are slight.
Do not invent separation between near-equivalent texts. Rank only recoverable stylistic resemblance;
list independently noticed semantic concerns separately without folding them into style scores.

For each key unit, describe the candidate's form difference and assign style_distance 0–3
(0=similarly close;1=minor;2=clear;3=large), or 0 for excluded units. Distances describe local form,
not counted errors. Units are selected explanations and MUST NOT be treated as an exhaustive
frequency measurement. Output JSON only. Do not rewrite whole translations or infer methods.
"""
UNIT_CANDIDATE = object_schema({"candidate_id": STRING, "quote": STRING, "form_difference": STRING,
                               "style_distance": {"type": "integer", "minimum": 0, "maximum": 3}})
UNIT = object_schema({"unit_id": STRING, "english_quote": STRING, "author_quote": STRING,
    "classification": {"type": "string", "enum": ["comparable_style", "terminology_only", "edition_content_difference", "uncertain"]},
    "focus": STRING, "rationale": STRING, "candidates": {"type": "array", "items": UNIT_CANDIDATE}})
ASSESSMENT = object_schema({"candidate_id": STRING, "scores": object_schema({d:SCORE for d in DIMENSIONS}),
    "not_assessable_dimensions": STRINGS, "reason": STRING, "semantic_concerns_not_in_style_score": STRINGS})
SCHEMA = object_schema({"units": {"type": "array", "items": UNIT},
    "assessments": {"type": "array", "items": ASSESSMENT},
    "ranking": {"type": "array", "items": STRINGS}, "limitations": STRINGS})


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def feedback_summary(state: dict, cases: dict[str, dict], mappings: dict) -> dict:
    credits = Counter({m:0.0 for m in study.METHODS})
    by_book, choices, rows, invalid = {}, Counter(), [], []
    for title in study.TITLES:
        by_book[title] = {"credits": {m:0.0 for m in study.METHODS}, "preferred":0, "tie":0, "none":0, "unrated":0, "skip":0, "planned":8}
    for key, vote in state["votes"].items():
        case = cases.get(key)
        expected = {c["id"]:{"output_sha256":c["output_sha256"], "text_sha256":c["text_sha256"]} for c in case["candidates"]} if case else None
        if not case or vote["display_manifest_sha256"] != case["display_manifest_sha256"] or vote["outputs"] != expected:
            invalid.append(key);continue
        methods = [mappings[case["sample_id"]]["候选"+label] for label in vote["candidate_ids"]]
        choice = vote["choice"]
        choices[choice] += 1; by_book[case["title"]][choice] += 1
        if choice in ("preferred","tie"):
            for method in methods:
                credits[method] += 1/len(methods)
                by_book[case["title"]]["credits"][method] += 1/len(methods)
        rows.append({"sample_id":case["sample_id"],"title":case["title"],"choice":choice,"methods":methods,
                     "note":vote["note"],"method_revealed":vote["method_revealed"],"updated_at":vote["updated_at"]})
    assert not invalid, invalid
    book_equal = {m:sum(b["credits"][m]/sum(b[x] for x in ("preferred","tie","none")) for b in by_book.values())/len(by_book)
                  for m in study.METHODS} if all(sum(b[x] for x in ("preferred","tie","none")) for b in by_book.values()) else None
    return {"record_count":len(state["votes"]),"choices":dict(choices),"preference_credits":dict(credits),
            "by_book":by_book,"partial_book_equal_credit":book_equal,"rows":rows,"invalid":invalid,
            "interpretation":"Partial human responses; notes do not become votes. Book-equal descriptive summary retains none as its own outcome, excludes skips/unrated/missing; not an unbiased full48 estimate."}


def prepare() -> None:
    if (ROOT/"manifest.json").exists():
        verify(ROOT/"manifest.json");return
    cases = reader.dataset()["cases"]
    assert len(cases)==48
    source = study.ROOT/"human_feedback/votes.json"
    snapshot = source.read_bytes()
    (ROOT/"human_snapshot").mkdir(parents=True,exist_ok=True)
    (ROOT/"human_snapshot/votes.json").write_bytes(snapshot)
    state = json.loads(snapshot)
    mapping = read(study.ROOT/"blind_mapping.json")
    summary = feedback_summary(state,{c["key"]:c for c in cases},mapping)
    write(ROOT/"human_summary.json",summary)
    rng = random.Random(SEED)
    jobs, identities, paths = [], {}, [ROOT/"human_snapshot/votes.json",ROOT/"human_summary.json",
            study.ROOT/"manifest.json", study.ROOT/"output_manifest.json", study.ROOT/"reader_manifest.json",
            study.ROOT/"audit/display_crops.json", Path(__file__), RESEARCH/"experiments/iteration7/runtime.py"]
    for case in cases:
        sid=case["sample_id"];sample=read(study.ROOT/f"samples/{sid}.json")
        groups={}
        for label,method in mapping[sid].items():
            paras=read(study.ROOT/f"outputs/{sid}/{method}.json")["paragraphs"]
            # Exact rendered text equivalence, including paragraph boundaries.
            groups.setdefault("\n".join(paras),{"paragraphs":paras,"methods":[]})["methods"].append(method)
        unique=list(groups.values());rng.shuffle(unique)
        identities[sid]={f"V{i+1}":g["methods"] for i,g in enumerate(unique)}
        candidates=[{"candidate_id":f"V{i+1}","paragraphs":g["paragraphs"]} for i,g in enumerate(unique)]
        base={"english_target":[x["english"] for x in sample["english"]],
              "english_context_before":sample["context_before"],"english_context_after":sample["context_after"],
              "author_chinese":case["author"]}
        for name,model,ordered in (("sol","gpt-5.6-sol",candidates),("terra","gpt-5.6-terra",list(reversed(candidates)))):
            path=ROOT/f"inputs/{sid}/{name}.json";write(path,{**base,"candidates":ordered});paths.append(path)
            jobs.append({"sample_id":sid,"reviewer":name,"model":model,"input":str(path.relative_to(ROOT))})
    write(ROOT/"identities.json",identities);paths.append(ROOT/"identities.json")
    write(ROOT/"manifest.json",{"created_at":datetime.now(UTC).isoformat(),"seed":SEED,"jobs":jobs,
        "bindings":binding(paths),"models":["gpt-5.6-sol","gpt-5.6-terra"],"dimensions":list(DIMENSIONS),
        "protocol":"All48 fixed scenes, two independent anonymous source-grounded judgments with reversed candidate order; exact duplicate rendered texts collapsed and reexpanded as ties. No human preferences, methods, existing ratings, or unverified edition ledger shown to judges.",
        "score":"Qualitative1–5 per dimension; average assessable dimensions and books equally, report each reviewer separately and pooled descriptive values. No style-recovery percent, no length/character similarity metric, no frequency inference from selected key units.",
        "calibration":"Rubric motivated by user's stated concerns and three examples016/017/018. Human agreement is descriptive on overlapping partial votes, not independent metric validation; separately report excluding those three.",
        "contrast_examples":"Diagnostic development evidence only. Do not train/tune on these and then claim same48 are heldout. OriginalChinese isn't automatically an English-faithful replacement."})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def verify(path: Path) -> dict:
    manifest=read(path)
    for name,expected in manifest["bindings"].items():
        file=Path(name) if Path(name).is_absolute() else REPO/name
        if sha(file)!=expected:raise RuntimeError(f"Frozen analysis input changed: {name}")
    return manifest


def run_one(job: dict) -> None:
    sid,reviewer=job["sample_id"],job["reviewer"]
    payload=read(ROOT/job["input"])
    result=invoke(ROOT,f"style/{sid}/{reviewer}",PROMPT,payload,SCHEMA,job["model"])
    write(ROOT/f"ratings/{sid}/{reviewer}.json",result)


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=["prepare","run","verify"])
    parser.add_argument("--workers",type=int,default=8);args=parser.parse_args()
    if args.stage=="prepare":prepare();return
    manifest=verify(ROOT/"manifest.json")
    if args.stage=="run" and not (ROOT/"ratings_manifest.json").exists():
        run_jobs(run_one,manifest["jobs"],args.workers)
        paths=list((ROOT/"ratings").rglob('*.json'))+list((ROOT/"calls").rglob('*.json'))+[ROOT/"manifest.json"]
        assert len(list((ROOT/"ratings").rglob('*.json')))==96
        write(ROOT/"ratings_manifest.json",{"frozen_at":datetime.now(UTC).isoformat(),"bindings":binding(paths)})
    if (ROOT/"ratings_manifest.json").exists():verify(ROOT/"ratings_manifest.json")
    print("Evaluation bindings verified")


if __name__=="__main__":main()
