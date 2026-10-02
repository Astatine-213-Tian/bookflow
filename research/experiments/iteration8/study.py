from __future__ import annotations

import argparse
import random
import re
import zipfile
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from bs4 import BeautifulSoup

from experiments.iteration6 import prompts as p
from experiments.iteration6.probe import METHODS, binding, chapter_paragraphs, run_jobs, windows, words
from experiments.iteration7.runtime import REPO, RESEARCH, invoke as call, read, sha, write

ROOT = RESEARCH / "generated/style_reading48_20260926"
PREVIOUS = RESEARCH / "generated/style_reading50_20260925"
BANK_ROOT = RESEARCH / "generated/style_probe6_20260925"
SEED = 2026092608
GENERATOR = "gpt-5.6-sol"
REVIEWER = "gpt-5.6-terra"
TITLES = ("乱世为王", "相见欢", "星盘重启", "江湾路七号男子宿舍", "定海浮生录", "天宝伏妖录")
invoke = partial(call, ROOT)


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def chapter_groups(chapters: list[dict]) -> list[dict]:
    groups = {}
    for chapter in chapters:
        number = int(str(chapter["en_chapter"]).split(".")[0])
        key = (chapter["volume"], number)
        if key not in groups:
            groups[key] = {**chapter, "en_chapter": number,
                           "en_members": list(chapter["en_members"]),
                           "source_chapter_labels": [str(chapter["en_chapter"])]}
        else:
            group = groups[key]
            assert group["en_epub_path"] == chapter["en_epub_path"]
            group["en_members"] = list(dict.fromkeys(group["en_members"] + chapter["en_members"]))
            group["clean_start_line"] = min(group["clean_start_line"], chapter["clean_start_line"])
            group["clean_end_line"] = max(group["clean_end_line"], chapter["clean_end_line"])
            group["source_chapter_labels"].append(str(chapter["en_chapter"]))
    return list(groups.values())


def source_rows(chapter: dict) -> tuple[list[dict], list[dict]]:
    """Keep old paragraph identities; remove only numeric linked endnote markers."""
    rows = chapter_paragraphs(chapter)
    replacements, changes = {}, []
    with zipfile.ZipFile(chapter["en_epub_path"]) as archive:
        for member in chapter["en_members"]:
            soup = BeautifulSoup(archive.read(member), "html.parser")
            nodes = soup.find_all("p") or soup.body.find_all("div", recursive=False)
            for index, node in enumerate(nodes):
                markers = [a for a in node.find_all("a", href=True)
                           if a.get_text(strip=True).isdigit()
                           and re.search(r"endnote|noteref|footnote", a["href"], re.I)]
                if not markers:
                    continue
                for marker in markers:
                    marker.decompose()
                for marker in node.select('sup, a[epub\\:type="noteref"]'):
                    marker.decompose()
                text = re.sub(r"\s+", " ", node.get_text("", strip=False)).strip()
                if node.select_one("span.calibre13"):
                    text = re.sub(r"^([A-Z]) ([A-Z]+)\b", r"\1\2", text, count=1)
                replacements[(member, index)] = text
    cleaned = []
    for row in rows:
        text = replacements.get((row["member"], row["p_index"]), row["english"])
        if text != row["english"]:
            changes.append({"member": row["member"], "p_index": row["p_index"], "before": row["english"], "after": text})
        cleaned.append({**row, "english": text})
    return cleaned, changes


def blocked_regions(chapter: dict, rows: list[dict], old_samples: list[dict], refs: list[dict]) -> list[tuple[int, int]]:
    identity = {(r["member"], r["p_index"]): i for i, r in enumerate(rows)}
    regions = []
    for sample in old_samples:
        if sample["source_epub"] != chapter["en_epub_path"]:
            continue
        indices = [identity[(r["member"], r["p_index"])] for r in sample["english"]
                   if (r["member"], r["p_index"]) in identity]
        if indices:
            regions.append((max(0, min(indices)-2), min(len(rows)-1, max(indices)+2)))
    for ref in refs:
        src = ref["sources"]
        if src["en_epub"] != chapter["en_epub_path"]:
            continue
        indices = [identity[(src["en_xhtml_member"], i)] for i in src["en_p_indexes_zero_based_all_p"]
                   if (src["en_xhtml_member"], i) in identity]
        if indices:
            regions.append((max(0, min(indices)-2), min(len(rows)-1, max(indices)+2)))
    return regions


def balanced_mappings(rng: random.Random, count: int = 8) -> list[dict]:
    """Two shuffled Williams blocks: each method occupies each position twice."""
    result = []
    for _ in range(count // 4):
        base = rng.sample(METHODS, 4)
        for order in ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1)):
            result.append({f"候选{chr(65+i)}": base[n] for i, n in enumerate(order)})
    rng.shuffle(result)
    return result


def verify_manifest(path: Path) -> dict:
    manifest = read(path)
    for name, expected in manifest["bindings"].items():
        resolved = Path(name) if Path(name).is_absolute() else REPO / name
        if sha(resolved) != expected:
            raise RuntimeError(f"Frozen input changed: {name}")
    return manifest


def prepare() -> None:
    if (ROOT / "manifest.json").exists():
        verify_manifest(ROOT / "manifest.json")
        print("Frozen 48-sample manifest verified")
        return
    source_path = ROOT / "structure/source_structure_hints.json"
    hints = read(source_path)
    books = {b["zh_title"]: b for b in hints["books"]}
    rng = random.Random(SEED)
    old_paths = sorted((BANK_ROOT / "samples").glob("*.json")) + sorted((PREVIOUS / "samples").glob("*.json"))
    old_samples = [read(path) for path in old_paths]
    ref_path = RESEARCH / "generated/style_reassessment_20260925/real_parallel_examples.json"
    refs = read(ref_path)["examples"]
    paths = [source_path, ref_path, BANK_ROOT / "authentic_examples.json", BANK_ROOT / "bank.json", *old_paths]
    frame, selected_by_book, normalizations = [], {}, []
    for title in TITLES:
        book = books[title]
        clean_path = RESEARCH / book["clean_path"]
        assert sha(clean_path) == book["clean_sha256"]
        clean = clean_path.read_text().splitlines()
        paths.append(clean_path)
        volumes = {}
        for chapter in chapter_groups(book["chapters"]):
            epub = Path(chapter["en_epub_path"])
            assert sha(epub) == chapter["en_epub_sha256"]
            paths.append(epub)
            rows, changes = source_rows(chapter)
            normalizations.extend({"title": title, "chapter": chapter["en_chapter"], **x} for x in changes)
            blocked = blocked_regions(chapter, rows, old_samples, refs)
            eligible = []
            for wi, span in enumerate(windows(rows)):
                region = (max(0, span[0]["index"]-2), min(len(rows)-1, span[-1]["index"]+2))
                entry = {"title": title, "volume": chapter["volume"], "chapter": chapter["en_chapter"],
                         "window": wi, "row_start": span[0]["index"], "row_end": span[-1]["index"],
                         "context_range": list(region), "eligible": not any(overlaps(region, r) for r in blocked)}
                frame.append(entry)
                if entry["eligible"]:
                    eligible.append((entry, span))
            if eligible:
                volumes.setdefault(chapter["volume"], []).append((chapter, rows, eligible))
        assert 8 % len(volumes) == 0
        quota = 8 // len(volumes)
        selected = []
        for volume, chapters in sorted(volumes.items()):
            assert len(chapters) >= quota
            for chapter, rows, eligible in rng.sample(chapters, quota):
                entry, span = rng.choice(eligible)
                sample = {**entry, "role": "exploratory_book_balanced", "source_epub": chapter["en_epub_path"],
                          "source_clean": str(clean_path), "english": span,
                          "english_words": sum(words(x["english"]) for x in span),
                          "context_before": [x["english"] for x in rows[max(0,span[0]["index"]-2):span[0]["index"]]],
                          "context_after": [x["english"] for x in rows[span[-1]["index"]+1:span[-1]["index"]+3]],
                          "eligible_chapters_in_volume": len(chapters), "volume_sample_quota": quota,
                          "chapter_selection_probability": quota/len(chapters),
                          "eligible_windows_in_chapter": len(eligible), "conditional_window_probability": 1/len(eligible),
                          "analysis_weight": 1/48}
                alignment = {"english": span, "chinese_search_region": [
                    {"line": i, "text": clean[i-1]} for i in range(chapter["clean_start_line"], chapter["clean_end_line"]+1)
                    if clean[i-1].strip()]}
                selected.append((sample, alignment))
        rng.shuffle(selected)
        selected_by_book[title] = selected
    mappings = {title: balanced_mappings(rng) for title in TITLES}
    draws, mapping = [], {}
    for index in range(8):
        order = rng.sample(list(TITLES), len(TITLES))
        for title in order:
            sample, alignment = selected_by_book[title][index]
            sid = f"balanced_{len(draws)+1:03d}"
            sample["sample_id"] = sid
            write(ROOT / f"samples/{sid}.json", sample)
            write(ROOT / f"alignment_inputs/{sid}.json", alignment)
            paths += [ROOT / f"samples/{sid}.json", ROOT / f"alignment_inputs/{sid}.json"]
            draws.append({k: v for k, v in sample.items() if k not in ("english", "context_before", "context_after")})
            mapping[sid] = mappings[title][index]
    for name, value in (("frame", frame), ("blind_mapping", mapping), ("footnote_normalizations", normalizations)):
        write(ROOT / f"{name}.json", value)
        paths.append(ROOT / f"{name}.json")
    paths += [Path(__file__), RESEARCH / "experiments/iteration7/runtime.py",
              RESEARCH / "experiments/iteration6/prompts.py", RESEARCH / "experiments/iteration6/probe.py",
              RESEARCH / "experiments/iteration5/pilot.py", REPO / "src/translation/style_transfer.py"]
    write(ROOT / "manifest.json", {"schema_version": 1, "seed": SEED, "created_at": datetime.now(UTC).isoformat(),
        "total_samples": 48, "books": list(TITLES), "samples_per_book": 8, "methods": METHODS,
        "draws": draws, "generator": GENERATOR, "reviewer": REVIEWER, "bindings": binding(paths),
        "sampling": "Six purposively selected books, eight passages each. Equal quotas across downloaded volumes; uniform distinct chapter groups per volume, then uniform eligible window within chapter. Fractional main-story chapters merged into their integer chapter before selection. Target and two-paragraph contexts excluded against previous probes and authentic reference passages. No result-based replacement.",
        "estimand": "Book-equal, volume-equal, chapter-equal within eligible volume frame, window-equal within chapter preference over six downloaded works. Not uniform author words or independent-book sample size48. Each observed item has weight1/48 under this multistage design.",
        "reference_exclusion": "Twin Jades remains reference-only: source of sole strict correction. Authentic Riverbay reference excluded for Riverbay targets; all four arms within a book share identical allowed references and correction bank. Old corpus split files unchanged; Dinghai/test and Tianbao/proxy now exposed in this exploratory reading study and cannot remain untouched tests for subsequent tuning on these results.",
        "feedback": "Old reader and votes archived, not forced into selection or aggregated into48. Chinese original visible; English source hidden. No human ratings fabricated.",
        "candidate_position_balance": "Two randomized Williams blocks per book; each method appears at each A-D position twice per book,12timesoverall. Each consecutive6itemscontainsall6books inseededrandomorder."})
    print(f"Prepared {len(draws)} samples across {len(frame)} windows", flush=True)


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
        raise RuntimeError(f"Alignment needs source review for fixed sample {sid}; no replacement")
    picked = [{"line": i, "text": t} for i, t in lines.items() if result["start_line"] <= i <= result["end_line"]]
    write(target, {**result, "usable": True, "lines": picked, "paragraphs": [x["text"] for x in picked]})


def generate(sid: str) -> None:
    sample = read(ROOT / f"samples/{sid}.json")
    refs = read(BANK_ROOT / "authentic_examples.json")
    refs = {**refs, "examples": [x for x in refs["examples"] if x["title"] != sample["title"]]}
    bank = read(BANK_ROOT / "bank.json")["prompt_examples"]
    assert all(x["title"] != sample["title"] for x in bank)
    base = {"sample_id": sid, "book": sample["title"],
            "english": [{"index": x["index"], "english": x["english"]} for x in sample["english"]],
            "context_before_do_not_translate": sample["context_before"], "context_after_do_not_translate": sample["context_after"],
            "authentic_examples": refs}
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "run", "verify"])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
        return
    manifest = verify_manifest(ROOT / "manifest.json")
    if args.stage == "run" and not (ROOT / "output_manifest.json").exists():
        run_jobs(process, [x["sample_id"] for x in manifest["draws"]], args.workers)
        paths = list((ROOT / "gold").glob("*.json")) + list((ROOT / "outputs").rglob("*.json"))
        assert len(list((ROOT / "outputs").glob("*/edited.json"))) == 48
        write(ROOT / "output_manifest.json", {"frozen_at": datetime.now(UTC).isoformat(),
              "bindings": binding(paths+[ROOT / "manifest.json", ROOT / "blind_mapping.json"])})
    if (ROOT / "output_manifest.json").exists():
        verify_manifest(ROOT / "output_manifest.json")
    print("Study bindings verified", flush=True)


if __name__ == "__main__":
    main()
