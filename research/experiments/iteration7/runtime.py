from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.translation.style_transfer import (
    _codex_binary, _minimal_child_environment, _parse_events, _sandbox_profile,
)
from experiments.iteration5.pilot import read, write, sha

RESEARCH = Path(__file__).resolve().parents[2]
REPO = RESEARCH.parent


def invoke(root: Path, name: str, prompt: str, payload: Any, schema: dict[str, Any], model: str) -> Any:
    out = root / f"calls/{name}.json"
    packet = {"prompt": prompt, "payload": payload, "schema": schema, "model": model}
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if out.exists():
        record = read(out)
        if record["input_sha256"] != digest: raise RuntimeError(f"Resume mismatch: {name}")
        return record["result"]
    write(root / f"requests/{name}.json", packet)
    failures = []
    for attempt in range(1, 3):
        with tempfile.TemporaryDirectory(prefix="style-pilot-") as tmp:
            temp = Path(tmp); schema_path = temp / "schema.json"; response = temp / "response.json"
            write(schema_path, schema)
            profile = temp / "isolation.sb"; profile.write_text(_sandbox_profile())
            cmd = ["/usr/bin/sandbox-exec", "-f", str(profile), str(_codex_binary("codex")), "exec",
                   "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                   "--dangerously-bypass-approvals-and-sandbox"]
            for feature in ("shell_tool", "unified_exec", "browser_use", "browser_use_external", "browser_use_full_cdp_access", "in_app_browser", "computer_use", "apps", "multi_agent"):
                cmd += ["--disable", feature]
            cmd += ["--cd", str(temp), "--model", model, "--config", 'model_reasoning_effort="high"',
                    "--output-schema", str(schema_path), "--output-last-message", str(response), "--json", "-"]
            try:
                process = subprocess.run(cmd, input=prompt + "\n\nDo not use tools or inspect files. Only use supplied data.\n" + json.dumps(payload, ensure_ascii=False),
                    text=True, capture_output=True, timeout=900, cwd=temp, env=_minimal_child_environment(temp))
                if process.returncode or not response.exists():
                    raise RuntimeError(f"exit {process.returncode}: {process.stderr[-500:]} {process.stdout[-500:]}")
                result = read(response)
                thread, usage, errors = _parse_events(process.stdout)
                write(out, {"input_sha256": digest, "model": model, "attempt": attempt, "response_id": thread,
                       "usage": usage, "prior_failures": failures, "completed_at": datetime.now(UTC).isoformat(), "result": result})
                print(f"complete {name}", flush=True)
                return result
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                failures.append(str(exc))
                write(root / f"failures/{name}.json", failures)
    raise RuntimeError(f"{name} failed: {failures}")

