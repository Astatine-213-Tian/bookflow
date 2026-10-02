from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from experiments.iteration6 import prompts as p
from experiments.iteration6.runtime import REPO, RESEARCH, ROOT, invoke, read, sha, write

SEED = 2026092506
STRATA = {"江东双璧": ("train", 6, "historical"), "星盘重启": ("train", 4, "speculative"),
          "江湾路七号男子宿舍": ("train", 2, "contemporary"),
          "乱世为王": ("dev", 3, "historical"), "相见欢": ("dev", 3, "historical")}
METHODS = ["direct", "positive", "contrastive", "edited"]
GENERATOR = "gpt-5.6-sol"
REVIEWER = "gpt-5.6-terra"
OLD_ROOT = RESEARCH / "generated/style_reassessment_20260925"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def words(text: str) -> int:
    return len(re.findall(r"\b[\w]+(?:['’\-][\w]+)*\b", text))


def chapter_paragraphs(chapter: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    with zipfile.ZipFile(chapter["en_epub_path"]) as archive:
        for member in chapter["en_members"]:
            soup = BeautifulSoup(archive.read(member), "html.parser")
            nodes = soup.find_all("p")
            if not nodes:
                # Kobo export encodes each paragraph as a sibling div of spans.
                nodes = soup.body.find_all("div", recursive=False)
            for index, node in enumerate(nodes):
                for footnote in node.select('sup, a[epub\\:type="noteref"]'):
                    footnote.decompose()
                text = re.sub(r"\s+", " ", node.get_text("", strip=False)).strip()
                if not re.search(r"[A-Za-z]", text):
                    continue
                if re.fullmatch(r"\[?chapter\s+\d+(?::[^\]]*)?\]?", text, re.I):
                    continue
                # Headings and image captions do not become translation windows.
                if any(re.search(r"title|caption|heading|chapter", x, re.I) for x in node.get("class", [])):
                    continue
                if "calibre9" in node.get("class", []) and soup.select("h2.calibre11"):
                    continue  # Astrolabe's chapter-title/blank paragraph class.
                if node.select_one("span.calibre13"):
                    text = re.sub(r"^([A-Z]) ([A-Z]+)\b", r"\1\2", text, count=1)
                rows.append({"index": len(rows), "member": member, "p_index": index, "english": text})
    return rows


def windows(rows: list[dict[str, Any]], *, target_words: int = 230) -> list[list[dict[str, Any]]]:
    result, current, count = [], [], 0
    for row in rows:
        current.append(row)
        count += words(row["english"])
        if count >= target_words:
            result.append(current)
            current, count = [], 0
    if current:
        if result and count < 120:
            result[-1].extend(current)
        else:
            result.append(current)
    return [x for x in result if sum(words(r["english"]) for r in x) >= 120]


def verify_bindings(path: Path) -> dict[str, Any]:
    manifest = read(path)
    remapping = {}
    amendment_path = ROOT / "continuation_manifest.json"
    if path == ROOT / "sampling_manifest.json" and amendment_path.exists():
        amendment = verify_bindings(amendment_path)
        assert sha(path) == amendment["sampling_manifest_sha256"]
        remapping = amendment["original_code_archives"]
        assert set(remapping) <= {"research/experiments/iteration6/probe.py", "research/experiments/iteration6/prompts.py"}
    for name, expected in manifest["bindings"].items():
        resolved = remapping.get(name, name)
        actual = Path(resolved) if Path(resolved).is_absolute() else REPO / resolved
        if sha(actual) != expected:
            raise RuntimeError(f"Frozen input changed: {name}")
    return manifest


def binding(paths: list[Path]) -> dict[str, str]:
    return {str(x.relative_to(REPO)) if x.is_relative_to(REPO) else str(x): sha(x) for x in sorted(set(paths))}


def prepare() -> None:
    lock = ROOT / "sampling_manifest.json"
    if lock.exists():
        verify_bindings(lock)
        print("Frozen sampling manifest verified", flush=True)
        return
    hints_path = ROOT / "source_structure_hints.json"
    hints = read(hints_path)
    by_title = {b["zh_title"]: b for b in hints["books"]}
    assert set(STRATA) <= set(by_title), set(STRATA) - set(by_title)
    splits_path = RESEARCH / "generated/style_research/corpus/splits.json"
    roles = {x["title"]: role for role, rows in read(splits_path).items() for x in rows
             if isinstance(rows, list) and x.get("author") == "非天夜翔"}
    rng = random.Random(SEED)
    frame, draws, paths = [], [], [hints_path, splits_path]
    old_examples = read(OLD_ROOT / "real_parallel_examples.json")
    # Keep the existing positive references but not their historical absolute hash claims.
    refs = [{k: x[k] for k in ("example_id", "title", "en", "zh")}
            for x in old_examples["examples"]]
    write(ROOT / "authentic_examples.json", {"examples": refs,
          "rule": old_examples["global_instructions"]})
    paths.append(ROOT / "authentic_examples.json")
    prior_spans = [(x["sources"]["en_epub"], x["sources"]["en_xhtml_member"],
                   set(x["sources"]["en_p_indexes_zero_based_all_p"])) for x in old_examples["examples"]]
    for title, (role, count, theme) in STRATA.items():
        assert roles[title] == role, (title, role, roles[title])
        book = by_title[title]
        clean_path = RESEARCH / book["clean_path"]
        assert sha(clean_path) == book["clean_sha256"]
        paths.append(clean_path)
        chapters = []
        for chapter in book["chapters"]:
            epub = Path(chapter["en_epub_path"])
            assert sha(epub) == chapter["en_epub_sha256"]
            paths.append(epub)
            rows = chapter_paragraphs(chapter)
            spans = windows(rows)
            eligible = []
            for wi, span in enumerate(spans):
                overlaps = any(str(epub) == path and any(r["member"] == member and r["p_index"] in ids for r in span)
                               for path, member, ids in prior_spans)
                entry = {"title": title, "chapter": chapter["en_chapter"], "window": wi,
                         "english_words": sum(words(r["english"]) for r in span),
                         "row_start": span[0]["index"], "row_end": span[-1]["index"],
                         "paragraph_sha256": digest(span),
                         "eligible": not overlaps,
                         "exclusion": "overlaps frozen positive reference" if overlaps else ""}
                frame.append(entry)
                if not overlaps:
                    eligible.append((entry, span))
            if eligible:
                chapters.append((chapter, rows, eligible))
        assert len(chapters) >= count, (title, len(chapters), count)
        selected = rng.sample(chapters, count)
        for chapter, rows, eligible in selected:
            entry, span = rng.choice(eligible)
            sid = f"{role}_{sum(x['role'] == role for x in draws) + 1:02d}"
            clean = clean_path.read_text().splitlines()
            start, end = chapter["clean_start_line"], chapter["clean_end_line"]
            search = [{"line": i, "text": clean[i-1]} for i in range(start, end+1) if clean[i-1].strip()]
            write(ROOT / f"samples/{sid}.json", {"sample_id": sid, "title": title, "role": role,
                "theme": theme, "chapter": chapter["en_chapter"], "english": span,
                "english_words": entry["english_words"],
                "context_before": [r["english"] for r in rows[max(0, span[0]["index"]-2):span[0]["index"]]],
                "context_after": [r["english"] for r in rows[span[-1]["index"]+1:span[-1]["index"]+3]],
                "source_epub": chapter["en_epub_path"],
                "source_clean": str(clean_path)})
            write(ROOT / f"alignment_inputs/{sid}.json", {"english": span, "chinese_search_region": search})
            paths += [ROOT / f"samples/{sid}.json", ROOT / f"alignment_inputs/{sid}.json"]
            draws.append({**entry, "sample_id": sid, "role": role, "theme": theme,
                          "chapter_selection_probability": count / len(chapters),
                          "conditional_window_probability": 1 / len(eligible)})
    write(ROOT / "sampling_frame.json", frame)
    paths.append(ROOT / "sampling_frame.json")
    paths += list(Path(__file__).parent.glob("*.py"))
    paths.append(RESEARCH / "experiments/iteration5/pilot.py")
    write(lock, {"version": 1, "seed": SEED, "frozen_at": datetime.now(UTC).isoformat(),
        "generator": GENERATOR, "reviewer": REVIEWER, "model_seed_supported": False,
        "strata": STRATA, "draws": draws, "bindings": binding(paths),
        "sampling_policy": "Theme-purposive book quotas, uniform distinct chapters within verified frame, then uniform non-overlapping paragraph windows within each chapter. No quality-based replacements.",
        "window_policy": "Accumulate complete paragraphs to >=230 English words; append tail <120 words to prior window; exclude old positive-reference overlaps before drawing.",
        "methods": METHODS, "bank_selection": "At most 8 accepted examples; round-robin title order, max 2 per sampled window, deterministic seeded order; no dev text used for selection.",
        "evidence_roles": "12 train windows for mining; 6 fresh dev windows; spent extra scenes and final-test/proxy books excluded. Both dev books historical.",
        "generation_boundary": "Target Chinese/edition ledger/alignment absent from generation, Chinese editor, and semantic QA; no target-gold glossary induction.",
        "evaluation": "Two source-only independent passes mark wording/meaning; one gold-aware style pass; opaque seeded labels and reversed source-judge order. English-word denominator, no Style Meter or length rewards. LLM judgments are exploratory."})
    print(json.dumps({"frame_windows": len(frame), "draws": draws}, ensure_ascii=False), flush=True)


def run_jobs(func: Any, jobs: list[Any], workers: int = 3) -> None:
    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(func, job): job for job in jobs}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                errors.append((futures[future], str(exc)))
                print(f"FAILED {futures[future]}: {exc}", flush=True)
    if errors:
        raise RuntimeError(errors)


def alignment(sid: str) -> None:
    payload = read(ROOT / f"alignment_inputs/{sid}.json")
    result = invoke(f"align/{sid}", p.ALIGN, payload, p.ALIGN_SCHEMA, GENERATOR)
    lines = {x["line"]: x["text"] for x in payload["chinese_search_region"]}
    valid = result["aligned"] and result["confidence"] == "high"
    valid = valid and result["start_line"] in lines and result["end_line"] in lines and result["start_line"] <= result["end_line"]
    selected = [{"line": i, "text": text} for i, text in lines.items()
                if result["start_line"] <= i <= result["end_line"]] if valid else []
    write(ROOT / f"gold/{sid}.json", {**result, "usable": valid, "lines": selected,
        "paragraphs": [x["text"] for x in selected], "source": "Existing clean corpus lines; not model-generated text."})


def base_payload(sample: dict[str, Any]) -> dict[str, Any]:
    return {"sample_id": sample["sample_id"], "book": sample["title"],
            "english": [{"index": r["index"], "english": r["english"]} for r in sample["english"]],
            "context_before_do_not_translate": sample["context_before"],
            "context_after_do_not_translate": sample["context_after"],
            "authentic_examples": read(ROOT / "authentic_examples.json")}


def mine(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    gold = read(ROOT / f"gold/{sid}.json")
    assert sample["role"] == "train"
    if not gold["usable"]:
        write(ROOT / f"mining/{sid}.json", {"status": "alignment_failure", "proposals": [], "excluded_observations": gold["boundary_notes"]})
        return
    direct = invoke(f"discovery/{sid}/direct", p.DIRECT, base_payload(sample), p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"discovery/{sid}.json", direct)
    payload = {"english": sample["english"], "draft": direct["paragraphs"],
               "author_chinese": gold["paragraphs"], "edition_notes": gold["edition_differences"]}
    mined = invoke(f"discovery/{sid}/mine", p.MINE, payload, p.MINE_SCHEMA, GENERATOR)
    draft_text = "\n".join(direct["paragraphs"])
    english = "\n".join(x["english"] for x in sample["english"])
    author = "\n".join(gold["paragraphs"])
    proposals, invalid = [], []
    for i, row in enumerate(mined["proposals"]):
        row = {**row, "example_id": f"{sid}_e{i+1:02d}", "sample_id": sid, "title": sample["title"], "theme": sample["theme"]}
        reasons = []
        for key, source in (("before", draft_text), ("english_support", english), ("author_anchor", author)):
            if not row[key].strip() or row[key] not in source:
                reasons.append(f"{key} is not an exact nonempty source span")
        if row["before"] == row["after"] or not row["after"].strip():
            reasons.append("repair empty or unchanged")
        if reasons:
            invalid.append({**row, "rejection_reasons": reasons})
        else:
            proposals.append(row)
    checked = invoke(f"discovery/{sid}/verify", p.VERIFY,
        {**payload, "proposals": proposals}, p.VERIFY_SCHEMA, REVIEWER) if proposals else {"decisions": []}
    decisions = {x["example_id"]: x for x in checked["decisions"]}
    assert set(decisions) == {x["example_id"] for x in proposals}
    reviewed = [{**x, "accepted": decisions[x["example_id"]]["accept"],
                 "review_reason": decisions[x["example_id"]]["reason"]} for x in proposals]
    write(ROOT / f"mining/{sid}.json", {"status": "reviewed", "proposals": reviewed,
        "invalid_exact_spans": invalid, "excluded_observations": mined["excluded_observations"]})


def freeze_bank() -> None:
    lock = ROOT / "bank_manifest.json"
    if lock.exists():
        verify_bindings(lock)
        print("Frozen bank verified", flush=True)
        return
    sampling = verify_bindings(ROOT / "sampling_manifest.json")
    accepted, rejected, ledger = [], [], []
    paths = [ROOT / "sampling_manifest.json"]
    for draw in sampling["draws"]:
        sid = draw["sample_id"]
        if draw["role"] != "train":
            continue
        path = ROOT / f"mining/{sid}.json"
        result = read(path)
        paths += [path, ROOT / f"gold/{sid}.json"]
        accepted.extend(x for x in result["proposals"] if x["accepted"])
        rejected.extend(x for x in result["proposals"] if not x["accepted"])
        rejected.extend(result.get("invalid_exact_spans", []))
        ledger.append({"sample_id": sid, "title": draw["title"], "status": result["status"],
            "english_words": draw["english_words"], "proposed": len(result["proposals"]) + len(result.get("invalid_exact_spans", [])),
            "accepted": sum(x["accepted"] for x in result["proposals"]), "excluded_observations": result["excluded_observations"]})
    rng = random.Random(SEED + 1)
    pools = {title: [x for x in accepted if x["title"] == title] for title in STRATA if STRATA[title][0] == "train"}
    for rows in pools.values():
        rng.shuffle(rows)
    chosen, counts = [], {}
    while any(pools.values()) and len(chosen) < 8:
        for title, rows in pools.items():
            while rows:
                row = rows.pop(0)
                if counts.get(row["sample_id"], 0) < 2:
                    chosen.append(row)
                    counts[row["sample_id"]] = counts.get(row["sample_id"], 0) + 1
                    break
            if len(chosen) == 8:
                break
    write(ROOT / "bank.json", {"accepted": accepted, "rejected": rejected,
        "prompt_examples": chosen, "ledger": ledger,
        "note": "Curated minimal translations; author anchors are evidence, not automatic targets. No target-dev material in this bank."})
    paths += [ROOT / "bank.json"]
    amendment_path = ROOT / "continuation_manifest.json"
    if amendment_path.exists():
        amendment = verify_bindings(amendment_path)
        paths += [amendment_path]
        paths += [Path(x) if Path(x).is_absolute() else REPO / x for x in amendment["bindings"]]
        paths += [REPO / x for x in amendment["original_code_archives"].values()]
    # Freeze gold and edition ledgers before candidates are available to evaluators.
    paths += [ROOT / f"gold/{d['sample_id']}.json" for d in sampling["draws"] if d["role"] == "dev"]
    write(lock, {"frozen_at": datetime.now(UTC).isoformat(), "bindings": binding(paths),
        "accepted": len(accepted), "rejected": len(rejected), "prompt_example_ids": [x["example_id"] for x in chosen]})
    print(f"Bank frozen: {len(accepted)} accepted, {len(rejected)} rejected; {len(chosen)} prompt examples", flush=True)


def generate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    assert sample["role"] == "dev"
    bank = read(ROOT / "bank.json")["prompt_examples"]
    base = base_payload(sample)
    direct = invoke(f"probe/{sid}/direct", p.DIRECT, base, p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"outputs/{sid}/direct.json", direct)
    positive_rows = [{"english_context": x["english_support"], "corrected_chinese_fragment": x["after"]} for x in bank]
    contrast_rows = [{"english_context": x["english_support"], "before": x["before"],
                      "corrected_chinese_fragment": x["after"], "reason": x["reason"]} for x in bank]
    positive = invoke(f"probe/{sid}/positive", p.DIRECT + p.POSITIVE,
        {**base, "wording_examples": positive_rows}, p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"outputs/{sid}/positive.json", positive)
    contrast = invoke(f"probe/{sid}/contrastive", p.DIRECT + p.CONTRAST,
        {**base, "wording_examples": contrast_rows}, p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"outputs/{sid}/contrastive.json", contrast)
    edit_rows = [{"before": x["before"], "after": x["after"], "reason": x["reason"]} for x in bank]
    edited = invoke(f"probe/{sid}/editor", p.EDIT,
        {"paragraphs": direct["paragraphs"], "training_contrasts": edit_rows}, p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"outputs/{sid}/edited_before_qa.json", edited)
    checked = invoke(f"probe/{sid}/semantic_qa", p.QA,
        {"english": base["english"], "context_before_do_not_translate": sample["context_before"],
         "context_after_do_not_translate": sample["context_after"], "edited_chinese": edited}, p.TEXT_SCHEMA, REVIEWER)
    write(ROOT / f"outputs/{sid}/edited.json", checked)


def freeze_outputs() -> None:
    if (ROOT / "output_manifest.json").exists():
        verify_bindings(ROOT / "output_manifest.json")
        return
    sampling = verify_bindings(ROOT / "sampling_manifest.json")
    verify_bindings(ROOT / "bank_manifest.json")
    rng = random.Random(SEED + 2)
    mappings, paths = {}, []
    for d in sampling["draws"]:
        if d["role"] != "dev":
            continue
        sid = d["sample_id"]
        shuffled = METHODS[:]
        rng.shuffle(shuffled)
        mappings[sid] = {f"候选{chr(65+i)}": method for i, method in enumerate(shuffled)}
        for method in METHODS + ["edited_before_qa"]:
            path = ROOT / f"outputs/{sid}/{method}.json"
            assert read(path)["paragraphs"]
            paths.append(path)
    write(ROOT / "blind_mapping.json", mappings)
    paths += [ROOT / "blind_mapping.json", ROOT / "bank_manifest.json"]
    write(ROOT / "output_manifest.json", {"frozen_at": datetime.now(UTC).isoformat(), "bindings": binding(paths)})


def evaluate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    gold = read(ROOT / f"gold/{sid}.json")
    mapping = read(ROOT / "blind_mapping.json")[sid]
    candidates = [{"candidate_id": label, "paragraphs": read(ROOT / f"outputs/{sid}/{method}.json")["paragraphs"]}
                  for label, method in mapping.items()]
    payload = {"english": sample["english"], "context_before": sample["context_before"],
               "context_after": sample["context_after"], "candidates": candidates}
    for judge, model in enumerate((REVIEWER, GENERATOR), 1):
        result = invoke(f"evaluate/{sid}/source_{judge}", p.SOURCE_JUDGE,
            {**payload, "candidates": candidates if judge == 1 else candidates[::-1]}, p.SOURCE_SCHEMA, model)
        assert {x["candidate_id"] for x in result["assessments"]} == set(mapping)
        write(ROOT / f"evaluation/{sid}/source_{judge}.json", result)
    if gold["usable"]:
        result = invoke(f"evaluate/{sid}/style", p.STYLE_JUDGE,
            {**payload, "author_chinese": gold["paragraphs"], "edition_differences": gold["edition_differences"],
             "boundary_notes": gold["boundary_notes"]}, p.STYLE_SCHEMA, REVIEWER)
        assert {x for group in result["ranking"] for x in group} == set(mapping)
        write(ROOT / f"evaluation/{sid}/style.json", result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "align", "mine", "freeze-bank", "generate", "evaluate", "verify"])
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
        return
    sampling = verify_bindings(ROOT / "sampling_manifest.json")
    if args.stage == "align":
        run_jobs(alignment, [d["sample_id"] for d in sampling["draws"]], args.workers)
    elif args.stage == "mine":
        run_jobs(mine, [d["sample_id"] for d in sampling["draws"] if d["role"] == "train"], args.workers)
    elif args.stage == "freeze-bank":
        freeze_bank()
    elif args.stage == "generate":
        verify_bindings(ROOT / "bank_manifest.json")
        run_jobs(generate, [d["sample_id"] for d in sampling["draws"] if d["role"] == "dev"], args.workers)
        freeze_outputs()
    elif args.stage == "evaluate":
        verify_bindings(ROOT / "bank_manifest.json")
        verify_bindings(ROOT / "output_manifest.json")
        run_jobs(evaluate, [d["sample_id"] for d in sampling["draws"] if d["role"] == "dev"], args.workers)
    elif args.stage == "verify":
        for name in ("bank_manifest", "output_manifest"):
            if (ROOT / f"{name}.json").exists():
                verify_bindings(ROOT / f"{name}.json")
        print("All available frozen bindings verified")


if __name__ == "__main__":
    main()
