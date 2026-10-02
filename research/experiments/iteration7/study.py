from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import zipfile
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from experiments.iteration6 import prompts as p
from experiments.iteration6.probe import METHODS, binding, chapter_paragraphs, run_jobs, windows, words
from experiments.iteration6.runtime import ROOT as PREVIOUS
from experiments.iteration7.runtime import REPO, RESEARCH, invoke as call, read, sha, write

ROOT = RESEARCH / "generated/style_reading50_20260925"
SEED = 2026092507
GENERATOR = "gpt-5.6-sol"
REVIEWER = "gpt-5.6-terra"
TITLES = ("乱世为王", "相见欢")
invoke = partial(call, ROOT)


def overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1])


def normalize_notes(chapter: dict, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    replacements, changes = {}, []
    with zipfile.ZipFile(chapter["en_epub_path"]) as archive:
        for member in chapter["en_members"]:
            soup = BeautifulSoup(archive.read(member), "html.parser")
            nodes = soup.find_all("p") or soup.body.find_all("div", recursive=False)
            for index, node in enumerate(nodes):
                markers = [n for n in node.find_all("span")
                           if re.search(r"vertical-align\s*:\s*super", n.get("style", ""), re.I)
                           and n.find("a", href=True) and n.get_text(strip=True).isdigit()]
                if not markers:
                    continue
                for marker in markers:
                    marker.decompose()
                for marker in node.select('sup, a[epub\\:type="noteref"]'):
                    marker.decompose()
                replacements[(member, index)] = re.sub(r"\s+", " ", node.get_text("", strip=False)).strip()
    cleaned = []
    for row in rows:
        text = replacements.get((row["member"], row["p_index"]), row["english"])
        if text != row["english"]:
            changes.append({"member": row["member"], "p_index": row["p_index"], "before": row["english"], "after": text})
        cleaned.append({**row, "english": text})
    return cleaned, changes


def verify() -> dict:
    manifest = read(ROOT / "manifest.json")
    for name, expected in manifest["bindings"].items():
        path = Path(name) if Path(name).is_absolute() else REPO / name
        if sha(path) != expected:
            raise RuntimeError(f"Frozen input changed: {name}")
    return manifest


def prepare() -> None:
    if (ROOT / "manifest.json").exists():
        verify()
        print("Frozen 50-sample manifest verified")
        return
    rng = random.Random(SEED)
    hints_path = PREVIOUS / "source_structure_hints.json"
    hints = read(hints_path)
    old = read(PREVIOUS / "sampling_manifest.json")
    splits_path = RESEARCH / "generated/style_research/corpus/splits.json"
    dev_titles = {x["title"] for x in read(splits_path)["dev"] if x["author"] == "非天夜翔"}
    assert set(TITLES) <= dev_titles
    paths = [hints_path, PREVIOUS / "sampling_manifest.json", splits_path,
             PREVIOUS / "bank.json", PREVIOUS / "bank_manifest.json",
             PREVIOUS / "authentic_examples.json", PREVIOUS / "output_manifest.json"]
    frame, selected_by_book, note_changes = [], {}, []
    for title in TITLES:
        book = next(x for x in hints["books"] if x["zh_title"] == title)
        clean_path = RESEARCH / book["clean_path"]
        assert sha(clean_path) == book["clean_sha256"]
        paths.append(clean_path)
        chapters, selected, used = {}, [], {}
        for ch in book["chapters"]:
            epub = Path(ch["en_epub_path"])
            assert sha(epub) == ch["en_epub_sha256"]
            paths.append(epub)
            original = chapter_paragraphs(ch)
            normalized, changes = normalize_notes(ch, original)
            note_changes += [{"title": title, "chapter": ch["en_chapter"], **x} for x in changes]
            normalized_map = {x["index"]: x for x in normalized}
            spans = windows(original)
            old_ranges = [(max(0, d["row_start"]-2), min(len(original)-1, d["row_end"]+2))
                          for d in old["draws"] if d["title"] == title and d["chapter"] == ch["en_chapter"]]
            eligible = []
            for wi, span in enumerate(spans):
                region = (max(0, span[0]["index"]-2), min(len(original)-1, span[-1]["index"]+2))
                blocked = any(overlaps(region, r) for r in old_ranges)
                entry = {"title": title, "chapter": ch["en_chapter"], "window": wi,
                         "row_start": span[0]["index"], "row_end": span[-1]["index"],
                         "context_range": region, "eligible": not blocked,
                         "exclusion": "overlap with prior six target/context" if blocked else ""}
                frame.append(entry)
                if not blocked:
                    eligible.append({**entry, "english": [normalized_map[r["index"]] for r in span]})
            assert eligible
            chapters[ch["en_chapter"]] = {"chapter": ch, "rows": normalized, "eligible": eligible}
            chosen = rng.choice(eligible)
            selected.append(chosen)
            used[ch["en_chapter"]] = [chosen["context_range"]]
        second_choices = []
        for number, ch in chapters.items():
            available = [x for x in ch["eligible"] if not any(overlaps(x["context_range"], r) for r in used[number])]
            if available:
                second_choices.append((number, available))
        for number, available in rng.sample(second_choices, 25-len(selected)):
            selected.append(rng.choice(available))
        assert len(selected) == 25
        rng.shuffle(selected)
        clean = clean_path.read_text().splitlines()
        selected_by_book[title] = []
        for d in selected:
            ch = chapters[d["chapter"]]
            rows, spec = ch["rows"], ch["chapter"]
            sample = {**d, "role": "dev", "cohort": "new50", "source_epub": spec["en_epub_path"],
                "source_clean": str(clean_path), "english_words": sum(words(x["english"]) for x in d["english"]),
                "context_before": [x["english"] for x in rows[max(0,d["row_start"]-2):d["row_start"]]],
                "context_after": [x["english"] for x in rows[d["row_end"]+1:d["row_end"]+3]]}
            alignment = {"english": sample["english"], "chinese_search_region": [
                {"line": i, "text": clean[i-1]} for i in range(spec["clean_start_line"], spec["clean_end_line"]+1)
                if clean[i-1].strip()]}
            selected_by_book[title].append((sample, alignment))
    draws, mapping = [], {}
    for i in range(25):
        for title in TITLES:
            sample, alignment = selected_by_book[title][i]
            sid = f"new_{len(draws)+1:03d}"
            sample["sample_id"] = sid
            write(ROOT / f"samples/{sid}.json", sample)
            write(ROOT / f"alignment_inputs/{sid}.json", alignment)
            paths += [ROOT / f"samples/{sid}.json", ROOT / f"alignment_inputs/{sid}.json"]
            draws.append({k: v for k, v in sample.items() if k not in ("english", "context_before", "context_after")})
            shuffled = METHODS[:]
            rng.shuffle(shuffled)
            mapping[sid] = {f"候选{chr(65+j)}": m for j,m in enumerate(shuffled)}
    for name, value in (("frame", frame), ("blind_mapping", mapping), ("footnote_normalizations", note_changes)):
        write(ROOT / f"{name}.json", value)
        paths.append(ROOT / f"{name}.json")
    paths += [Path(__file__), Path(__file__).with_name("runtime.py"),
              RESEARCH / "experiments/iteration6/prompts.py", RESEARCH / "experiments/iteration6/probe.py",
              RESEARCH / "experiments/iteration5/pilot.py", REPO / "src/translation/style_transfer.py"]
    write(ROOT / "manifest.json", {"schema_version": 1, "seed": SEED, "created_at": datetime.now(UTC).isoformat(),
        "new_samples": 50, "legacy_samples_separate": 6, "methods": METHODS, "draws": draws,
        "generator": GENERATOR, "reviewer": REVIEWER, "model_seed_supported": False,
        "bindings": binding(paths),
        "sampling": "25 per dev book; one seeded-uniform window in every eligible English chapter, then seeded selection of distinct chapters for a second context-disjoint window. Whole windows plus two paragraphs either side excluded against previous and new draws. No quality-based replacement.",
        "scope": "35 chapters in two historical dev books; 50 passages are not 50 independent books. Old six remain separate spent development. No test/proxy books or new mined examples.",
        "methods_unchanged": "Exact iteration6 generation/edit/QA prompts and same frozen one-example bank. Narrow source footnote normalization documented; no target Chinese in generation/edit/QA.",
        "human_review": "Author Chinese visible, methods anonymous until reveal. Source-aware reader preference, not fully blind evaluation. Feedback is never fabricated; clicks bound to exact sample/candidate/output hashes."})
    print(f"Prepared {len(draws)} fresh samples, {len(frame)} frame windows, {len(note_changes)} source footnote normalizations", flush=True)


def align(sid: str) -> None:
    target = ROOT / f"gold/{sid}.json"
    if target.exists():
        assert read(target)["usable"]
        return
    payload = read(ROOT / f"alignment_inputs/{sid}.json")
    result = invoke(f"align/{sid}", p.ALIGN, payload, p.ALIGN_SCHEMA, GENERATOR)
    lines = {x["line"]: x["text"] for x in payload["chinese_search_region"]}
    valid = result["aligned"] and result["confidence"] == "high" and result["start_line"] in lines and result["end_line"] in lines and result["start_line"] <= result["end_line"]
    if not valid:
        write(ROOT / f"alignment_needs_review/{sid}.json", result)
        raise RuntimeError(f"Alignment requires review: {sid}; no replacement draw")
    picked = [{"line": i, "text": t} for i,t in lines.items() if result["start_line"] <= i <= result["end_line"]]
    write(target, {**result, "usable": True, "lines": picked, "paragraphs": [x["text"] for x in picked]})


def generate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    base = {"sample_id": sid, "book": sample["title"],
        "english": [{"index": x["index"], "english": x["english"]} for x in sample["english"]],
        "context_before_do_not_translate": sample["context_before"], "context_after_do_not_translate": sample["context_after"],
        "authentic_examples": read(PREVIOUS / "authentic_examples.json")}
    bank = read(PREVIOUS / "bank.json")["prompt_examples"]
    positive = [{"english_context": x["english_support"], "corrected_chinese_fragment": x["after"]} for x in bank]
    contrasts = [{**a, "before": b["before"], "reason": b["reason"]} for a,b in zip(positive, bank)]
    for method, prompt, payload in (("direct", p.DIRECT, base),
        ("positive", p.DIRECT+p.POSITIVE, {**base, "wording_examples": positive}),
        ("contrastive", p.DIRECT+p.CONTRAST, {**base, "wording_examples": contrasts})):
        result = invoke(f"probe/{sid}/{method}", prompt, payload, p.TEXT_SCHEMA, GENERATOR)
        assert result["paragraphs"] and all(x.strip() for x in result["paragraphs"])
        write(ROOT / f"outputs/{sid}/{method}.json", result)
    direct = read(ROOT / f"outputs/{sid}/direct.json")
    edited = invoke(f"probe/{sid}/editor", p.EDIT, {"paragraphs": direct["paragraphs"],
        "training_contrasts": [{"before": x["before"], "after": x["after"], "reason": x["reason"]} for x in bank]}, p.TEXT_SCHEMA, GENERATOR)
    write(ROOT / f"outputs/{sid}/edited_before_qa.json", edited)
    checked = invoke(f"probe/{sid}/semantic_qa", p.QA, {"english": base["english"],
        "context_before_do_not_translate": sample["context_before"], "context_after_do_not_translate": sample["context_after"],
        "edited_chinese": edited}, p.TEXT_SCHEMA, REVIEWER)
    assert checked["paragraphs"] and all(x.strip() for x in checked["paragraphs"])
    write(ROOT / f"outputs/{sid}/edited.json", checked)


def process(sid: str) -> None:
    align(sid)
    generate(sid)
    print(f"READY {sid}", flush=True)


def freeze_outputs() -> None:
    paths = list((ROOT / "outputs").rglob("*.json")) + list((ROOT / "gold").glob("*.json"))
    assert len(list((ROOT / "gold").glob("*.json"))) == 50
    assert len(list((ROOT / "outputs").glob("*/edited.json"))) == 50
    paths += [ROOT / "manifest.json", ROOT / "blind_mapping.json"]
    write(ROOT / "output_manifest.json", {"frozen_at": datetime.now(UTC).isoformat(), "bindings": binding(paths)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "run", "verify"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
        return
    manifest = verify()
    if args.stage == "run":
        if (ROOT / "output_manifest.json").exists():
            print("Outputs already frozen; run verify")
            return
        run_jobs(process, [x["sample_id"] for x in manifest["draws"]], args.workers)
        freeze_outputs()
    if (ROOT / "output_manifest.json").exists():
        for name, expected in read(ROOT / "output_manifest.json")["bindings"].items():
            assert sha(REPO / name) == expected, name
    print("All available study bindings verified")


if __name__ == "__main__":
    main()
