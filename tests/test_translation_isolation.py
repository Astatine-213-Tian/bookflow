from __future__ import annotations

import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.translation.style_transfer import _sandbox_profile, run_structured_attempt


class TranslationIsolationTests(unittest.TestCase):
    def test_structured_session_disables_memory_without_changing_global_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            original = "[features]\nmemories = true\n"
            config.write_text(original)
            schema = root / "schema.json"
            schema.write_text('{"type": "object"}')

            def run_child(command, **kwargs):
                overrides = dict(
                    command[i + 1].split("=", 1)
                    for i, value in enumerate(command[:-1])
                    if value == "--config"
                )
                disabled = {
                    command[i + 1]
                    for i, value in enumerate(command[:-1])
                    if value == "--disable"
                }
                self.assertIn("memories", disabled)
                self.assertIn("plugins", disabled)
                self.assertIn("external_agent_memory_import", disabled)
                self.assertEqual(overrides["memories.use_memories"], "false")
                self.assertEqual(overrides["memories.generate_memories"], "false")
                self.assertEqual(overrides["project_doc_max_bytes"], "0")
                self.assertEqual(overrides["web_search"], '"disabled"')
                self.assertIn("--ignore-user-config", command)
                self.assertIn("--ephemeral", command)
                self.assertNotIn("resume", command)
                self.assertNotIn("fork", command)
                self.assertEqual(kwargs["env"]["CODEX_HOME"], str(root))
                self.assertNotIn("CODEX_THREAD_ID", kwargs["env"])
                self.assertNotEqual(kwargs["cwd"], root)
                response = Path(command[command.index("--output-last-message") + 1])
                response.write_text('{"paragraphs": ["门开了。"]}')
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.dict(
                    "os.environ",
                    {"CODEX_HOME": str(root), "CODEX_THREAD_ID": "parent-thread"},
                ),
                patch(
                    "src.translation.style_transfer._codex_binary",
                    return_value=Path("codex"),
                ),
                patch(
                    "src.translation.style_transfer.subprocess.run",
                    side_effect=run_child,
                ),
            ):
                record = run_structured_attempt(
                    request={"english": "The door opened."},
                    prompt_template="Translate only the supplied English.",
                    schema_path=schema,
                    output_path=root / "result.json",
                    model="test-model",
                    reasoning_effort="high",
                    timeout_seconds=10,
                    codex_bin="codex",
                    attempt=1,
                    result_validator=lambda request, result: [],
                )
            self.assertEqual(record["status"], "success")
            self.assertEqual(config.read_text(), original)

    @unittest.skipUnless(
        platform.system() == "Darwin" and Path("/usr/bin/sandbox-exec").exists(),
        "macOS filesystem isolation",
    )
    def test_sandbox_blocks_saved_context_but_keeps_session_files_accessible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            user_home = root / "user"
            codex_home = user_home / 'codex "profile"'
            protected = [
                codex_home / "memories/memory_summary.md",
                codex_home / "sessions/previous.jsonl",
                codex_home / "archived_sessions/previous.jsonl",
                codex_home / "AGENTS.md",
                codex_home / "AGENTS.override.md",
                codex_home / "skills/example/SKILL.md",
                user_home / ".agents/skills/example/SKILL.md",
                root / "repo/private-source.txt",
            ]
            for path in protected:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("PRIVATE_CONTEXT_CANARY")
            session_file = root / "session/input.json"
            session_file.parent.mkdir()
            session_file.write_text("EXPLICIT_SESSION_INPUT")
            config = codex_home / "config.toml"
            config.write_text("[features]\nmemories = true\n")
            with (
                patch.dict("os.environ", {"CODEX_HOME": str(codex_home)}),
                patch(
                    "src.translation.style_transfer.Path.home", return_value=user_home
                ),
                patch(
                    "src.translation.style_transfer.repo_root", return_value=root / "repo"
                ),
            ):
                profile = _sandbox_profile()
            profile_path = root / "isolation.sb"
            profile_path.write_text(profile)
            for path in protected:
                with self.subTest(path=path.relative_to(root)):
                    result = subprocess.run(
                        [
                            "/usr/bin/sandbox-exec", "-f", str(profile_path),
                            "/bin/cat", str(path),
                        ],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("PRIVATE_CONTEXT_CANARY", result.stdout)
            # Session isolation must not change the global memory switch or
            # contribute new memories, even if the child tries to write them.
            for path in (config, codex_home / "memories/new.md"):
                with self.subTest(write=path.relative_to(root)):
                    result = subprocess.run(
                        [
                            "/usr/bin/sandbox-exec", "-f", str(profile_path),
                            "/usr/bin/touch", str(path),
                        ],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
            self.assertEqual(config.read_text(), "[features]\nmemories = true\n")
            self.assertFalse((codex_home / "memories/new.md").exists())
            result = subprocess.run(
                [
                    "/usr/bin/sandbox-exec", "-f", str(profile_path),
                    "/bin/cat", str(session_file),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "EXPLICIT_SESSION_INPUT")


if __name__ == "__main__":
    unittest.main()
