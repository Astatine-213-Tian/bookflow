from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime
from pathlib import Path

from experiments.iteration6.probe import binding, windows, words
from experiments.iteration7.runtime import RESEARCH, REPO, read, sha, write
from experiments.iteration8 import study as prior
from experiments.iteration9 import study as paired_prior

ROOT = RESEARCH / "generated/style_direct_positive48_20261001"
SEED = 2026100110
METHODS = ("direct", "positive")
TITLES = prior.TITLES
GENERATOR = prior.GENERATOR
REVIEWER = prior.REVIEWER
verify_manifest = prior.verify_manifest


def paired_mappings(rng: random.Random) -> list[dict]:
    first = [True, False]
    rest = [True] * 3 + [False] * 3
    rng.shuffle(first)
    rng.shuffle(rest)
    return [{"候选A": "direct" if old_first else "positive", "候选B": "positive" if old_first else "direct"}
            for old_first in first + rest]


def interleave_volumes(selected: list[tuple], rng: random.Random) -> list[tuple]:
    volumes = {}
    for item in selected:
        volumes.setdefault(item[0]["volume"], []).append(item)
    for items in volumes.values():
        rng.shuffle(items)
    ordered = []
    while any(volumes.values()):
        for volume in rng.sample([v for v, rows in volumes.items() if rows], sum(bool(rows) for rows in volumes.values())):
            ordered.append(volumes[volume].pop())
    return ordered



def prepare() -> None:
    if (ROOT / "manifest.json").exists():
        verify_manifest(ROOT / "manifest.json")
        print("Frozen direct/positive study verified")
        return
    prior.verify_manifest(prior.ROOT / "manifest.json")
    prior.verify_manifest(prior.ROOT / "output_manifest.json")
    paired_prior.verify_manifest(paired_prior.ROOT / "manifest.json")
    paired_prior.verify_manifest(paired_prior.ROOT / "output_manifest.json")
    hints_path = prior.ROOT / "structure/source_structure_hints.json"
    books = {b["zh_title"]: b for b in read(hints_path)["books"]}
    old_paths = [p for root in (prior.BANK_ROOT, prior.PREVIOUS, prior.ROOT, paired_prior.ROOT) for p in sorted((root / "samples").glob("*.json"))]
    old_samples = [read(p) for p in old_paths]
    ref_path = RESEARCH / "generated/style_reassessment_20260925/real_parallel_examples.json"
    refs = read(ref_path)["examples"]
    paths = [hints_path, ref_path, paired_prior.ROOT / "manifest.json", paired_prior.ROOT / "output_manifest.json",
             prior.BANK_ROOT / "authentic_examples.json", prior.BANK_ROOT / "bank.json", *old_paths]
    rng = random.Random(SEED)
    frame, selected_by_book, normalizations = [], {}, []
    for title in TITLES:
        book = books[title]
        clean_path = RESEARCH / book["clean_path"]
        assert sha(clean_path) == book["clean_sha256"]
        paths.append(clean_path)
        clean = clean_path.read_text().splitlines()
        volumes = {}
        for chapter in prior.chapter_groups(book["chapters"]):
            epub = Path(chapter["en_epub_path"])
            assert sha(epub) == chapter["en_epub_sha256"]
            paths.append(epub)
            rows, changes = prior.source_rows(chapter)
            normalizations.extend({"title": title, "chapter": chapter["en_chapter"], **x} for x in changes)
            blocked = prior.blocked_regions(chapter, rows, old_samples, refs)
            eligible = []
            for wi, span in enumerate(windows(rows)):
                region = (max(0, span[0]["index"] - 2), min(len(rows) - 1, span[-1]["index"] + 2))
                entry = {"title": title, "volume": chapter["volume"], "chapter": chapter["en_chapter"],
                         "window": wi, "row_start": span[0]["index"], "row_end": span[-1]["index"],
                         "context_range": list(region), "eligible": not any(prior.overlaps(region, r) for r in blocked)}
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
                sample = {**entry, "role": "fresh_passage_paired_development", "source_epub": chapter["en_epub_path"],
                          "source_clean": str(clean_path), "english": span,
                          "english_words": sum(words(x["english"]) for x in span),
                          "context_before": [x["english"] for x in rows[max(0, span[0]["index"] - 2):span[0]["index"]]],
                          "context_after": [x["english"] for x in rows[span[-1]["index"] + 1:span[-1]["index"] + 3]],
                          "eligible_chapters_in_volume": len(chapters), "volume_sample_quota": quota,
                          "chapter_selection_probability": quota / len(chapters),
                          "eligible_windows_in_chapter": len(eligible), "conditional_window_probability": 1 / len(eligible),
                          "analysis_weight": 1 / 48}
                alignment = {"english": span, "chinese_search_region": [
                    {"line": i, "text": clean[i - 1]} for i in range(chapter["clean_start_line"], chapter["clean_end_line"] + 1)
                    if clean[i - 1].strip()]}
                selected.append((sample, alignment))
        selected_by_book[title] = interleave_volumes(selected, rng)
    mappings = {title: paired_mappings(rng) for title in TITLES}
    draws, mapping = [], {}
    for index in range(8):
        for title in rng.sample(list(TITLES), len(TITLES)):
            sample, alignment = selected_by_book[title][index]
            sid = f"dp_{len(draws) + 1:03d}"
            sample["sample_id"] = sid
            sample["reading_stage"] = "first12" if index < 2 else "remaining36"
            write(ROOT / f"samples/{sid}.json", sample)
            write(ROOT / f"alignment_inputs/{sid}.json", alignment)
            paths += [ROOT / f"samples/{sid}.json", ROOT / f"alignment_inputs/{sid}.json"]
            draws.append({k: v for k, v in sample.items() if k not in ("english", "context_before", "context_after")})
            mapping[sid] = mappings[title][index]
    for name, value in (("frame", frame), ("blind_mapping", mapping), ("footnote_normalizations", normalizations)):
        write(ROOT / f"{name}.json", value)
        paths.append(ROOT / f"{name}.json")
    paths += [Path(__file__), Path(__file__).with_name("pipeline.py"), Path(__file__).with_name("prompts.py"),
              RESEARCH / "experiments/iteration8/study.py", RESEARCH / "experiments/iteration9/study.py",
              RESEARCH / "experiments/iteration9/pipeline.py", RESEARCH / "experiments/iteration9/prompts.py", RESEARCH / "experiments/iteration7/runtime.py",
              RESEARCH / "experiments/iteration6/prompts.py", RESEARCH / "experiments/iteration6/probe.py",
              RESEARCH / "experiments/iteration5/pilot.py", REPO / "src/translation/style_transfer.py"]
    write(ROOT / "manifest.json", {"schema_version": 1, "seed": SEED, "created_at": datetime.now(UTC).isoformat(),
        "total_samples": 48, "books": list(TITLES), "samples_per_book": 8, "methods": METHODS,
        "draws": draws, "generator": GENERATOR, "reviewer": REVIEWER, "bindings": binding(paths),
        "sampling": "Same fixed volume/chapter/window design as iteration8, additionally excludes all iteration8 and iteration9 targets and two-paragraph contexts. Fresh passages, not unseen books or chapters. No output-quality replacement.",
        "estimand": "Book-equal, volume-equal, chapter-equal within volume, eligible-window-equal paired preference over six downloaded books.48 passages, not48 independent books.",
        "intervention": "Unchanged iteration8 direct versus positive full-scene generation. Identical English/context and authentic references; positive adds only the original accepted positive wording example. Independent single generations, no editor or corrective QA. Additional reading examples, not expansion of the prompt example bank.",
        "source_boundary": "Target author Chinese is only used for literal source alignment/display, never generation or QA. Authentic references and the original wording bank exclude target book; no iteration9 cards are used. Existing corpus splits and production outputs unchanged.",
        "reading_stages": "All48 frozen before generation. First12 have2/book and direct/positive once each atA per book; remaining36 have6/book,3atA each. First12 is a reading checkpoint, not a separately validated improvement trial. Changing method after its feedback requires a new version; do not pool versions.",
        "evaluation": "Independent source-only anonymous pair review after both outputs; no automatic style winner or score-based edits. Human source-visible, method-blind preferences are endpoint. Report semantic concerns separately.",
        "feedback": "New batch and storage. Old votes remain separate, no carried preferences or synthetic human feedback."})
    print(f"Prepared {len(draws)} paired scenes; {sum(x['eligible'] for x in frame)} eligible windows", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "verify"])
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
    else:
        verify_manifest(ROOT / "manifest.json")
        if (ROOT / "output_manifest.json").exists():
            verify_manifest(ROOT / "output_manifest.json")
        print("Paired study bindings verified")


if __name__ == "__main__":
    main()
