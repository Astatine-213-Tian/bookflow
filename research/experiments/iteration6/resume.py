"""Safe entry point that preserves independently curated and frozen stage outputs."""
from __future__ import annotations

import sys

from experiments.iteration6 import probe


def frozen_stage_exists(stage: str) -> bool:
    required = {
        "align": "bank_manifest.json",
        "mine": "bank_manifest.json",
        "generate": "output_manifest.json",
        "evaluate": "evaluation_manifest.json",
    }.get(stage)
    if required is None or not (probe.ROOT / required).exists():
        return False
    probe.verify_bindings(probe.ROOT / "sampling_manifest.json")
    probe.verify_bindings(probe.ROOT / required)
    return True


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "verify" and (probe.ROOT / "evaluation_manifest.json").exists():
        probe.verify_bindings(probe.ROOT / "evaluation_manifest.json")
    if frozen_stage_exists(stage):
        print(f"{stage}: frozen artifacts verified and preserved")
        return
    probe.main()


if __name__ == "__main__":
    main()
