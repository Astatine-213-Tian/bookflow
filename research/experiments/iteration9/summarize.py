"""Describe the frozen paired run without inventing a style score or winner."""
from __future__ import annotations

from collections import Counter

from experiments.iteration9.study import ROOT, read, sha, verify_manifest, write


def main() -> None:
    manifest = verify_manifest(ROOT / "manifest.json")
    verify_manifest(ROOT / "output_manifest.json")
    counts = Counter()
    concern_counts = {method: Counter() for method in ("old", "new")}
    rows = []
    for draw in manifest["draws"]:
        sid = draw["sample_id"]
        sample = read(ROOT / f"samples/{sid}.json")
        stages = ROOT / f"stages/{sid}"
        edited = read(stages / "new_editor_patches.json")
        qa = read(stages / "new_qa_proposals.json")
        decisions = read(stages / "qa_decisions.json")
        provenance = read(stages / "provenance.json")
        row = {"sample_id": sid, "title": sample["title"], "reading_stage": sample["reading_stage"],
               "editor_patches": len(edited["patches"]), "qa_proposed": len(qa["patches"]),
               "qa_accepted": decisions["accepted_count"], "identical": provenance["final_texts_identical"]}
        counts.update({"pairs": 1, "editor_patches": row["editor_patches"],
                       "qa_proposed": row["qa_proposed"], "qa_accepted": row["qa_accepted"],
                       "identical_pairs": int(row["identical"]),
                       "zero_editor_patch_scenes": int(not row["editor_patches"])})
        evaluation = read(ROOT / f"evaluations/{sid}.json")
        for assessment in evaluation["result"]["assessments"]:
            method = evaluation["mapping"][assessment["candidate_id"]]
            for kind in ("wording_errors", "meaning_errors"):
                concerns = assessment[kind]
                concern_counts[method][kind] += len(concerns)
                concern_counts[method][kind + "_scenes"] += bool(concerns)
        rows.append(row)
    counts["qa_rejected"] = counts["qa_proposed"] - counts["qa_accepted"]
    output = {"input_manifest_sha256": sha(ROOT / "manifest.json"),
              "output_manifest_sha256": sha(ROOT / "output_manifest.json"),
              "counts": dict(counts), "model_concerns": concern_counts, "scenes": rows,
              "saved_requests": len(list((ROOT / "requests").rglob("*.json"))),
              "format_issues": [str(path.relative_to(ROOT)) for path in sorted((ROOT / "format_issues").rglob("*.json"))],
              "interpretation": "Counts describe one frozen pipeline run. Model concerns are uncalibrated allegations, not verified error rates, style scores, human preferences, or a method winner. Read the independent audit."}
    write(ROOT / "summary.json", output)
    print({"counts": dict(counts), "requests": output["saved_requests"], "model_concerns": concern_counts})


if __name__ == "__main__":
    main()
