#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "codex-wiring.py"
type JsonValue = str | int | bool | None | list[JsonValue] | dict[str, JsonValue]

spec = importlib.util.spec_from_file_location("codex_wiring", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
cw = importlib.util.module_from_spec(spec)
sys.modules["codex_wiring"] = cw
spec.loader.exec_module(cw)


class CodexWiring(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        self.tmp: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.codex_home: pathlib.Path = pathlib.Path(self.tmp.name) / "codex"

    def setUp(self) -> None:
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.codex_home = pathlib.Path(self.tmp.name) / "codex"
        self.codex_home.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_config(self, text: str) -> None:
        (self.codex_home / "config.toml").write_text(text, encoding="utf-8")

    def write_hooks(self, obj: dict[str, JsonValue]) -> None:
        (self.codex_home / "hooks.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--codex-home", str(self.codex_home), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_check_reports_missing_wiring_when_config_exists(self) -> None:
        self.write_config('model = "user-model"\n')
        self.write_hooks({"hooks": {}})

        result = self.run_cli("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("would update config.toml", result.stdout)
        self.assertIn("would update hooks.json", result.stdout)

    def test_apply_is_idempotent_and_preserves_existing_entries(self) -> None:
        self.write_config(
            '# keep this comment\n'
            'model = "user-model"\n'
            'approval_policy = "never"\n'
            'sandbox_mode = "danger-full-access"\n'
            '\n'
            '[projects."/repo"]\n'
            'trust_level = "trusted"\n'
            '\n'
            '[tui]\n'
            '# keep tui note\n'
            'status_line = [\n'
            '  "model-with-reasoning",\n'
            ']\n'
            '\n'
            '[hooks.state."/tmp/hooks.json:stop:0:0"]\n'
            'trusted_hash = "sha256:abc"\n'
            'enabled = false\n'
        )
        existing: dict[str, JsonValue] = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": '"/opt/node" "/opt/omx/codex-native-hook.js"',
                            },
                        ],
                    },
                ],
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": '"/opt/node" "/opt/omx/codex-native-hook.js"',
                                "timeout": 30,
                            },
                        ],
                    },
                ],
            },
        }
        self.write_hooks(existing)

        first = self.run_cli("--apply")
        second = self.run_cli("--apply")
        check = self.run_cli("--check")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

        config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('# keep this comment\nmodel = "user-model"', config)
        self.assertIn('approval_policy = "never"', config)
        self.assertIn('sandbox_mode = "danger-full-access"', config)
        self.assertIn('[projects."/repo"]\ntrust_level = "trusted"', config)
        self.assertIn('trusted_hash = "sha256:abc"', config)
        self.assertIn('enabled = false', config)
        self.assertIn('[mcp_servers.agentic_memory]', config)
        self.assertIn('url = "http://127.0.0.1:8765/mcp"', config)
        self.assertIn('startup_timeout_sec = 30', config)
        self.assertIn('tool_timeout_sec = 60', config)
        self.assertIn('required = false', config)
        self.assertIn(
            'status_line = ["context-remaining", "five-hour-limit", "weekly-limit", '
            '"used-tokens", "estimated-thread-cost", "git-branch"]',
            config,
        )

        hooks = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
            '"/opt/node" "/opt/omx/codex-native-hook.js"',
        )
        commands = [
            handler["command"]
            for group in hooks["hooks"]["UserPromptSubmit"]
            for handler in group["hooks"]
        ]
        self.assertIn('"$HOME"/.local/bin/agent-memory-hook recall_prompt', commands)
        self.assertIn('"$HOME"/.local/bin/agent-memory-hook capture', commands)
        self.assertEqual(commands.count('"$HOME"/.local/bin/agent-memory-hook capture'), 1)
        recall_prompt = hooks["hooks"]["UserPromptSubmit"][2]["hooks"][0]
        session_start = hooks["hooks"]["SessionStart"][0]
        session_end = hooks["hooks"]["SessionEnd"][0]["hooks"][0]
        preserve = hooks["hooks"]["PreCompact"][0]["hooks"][0]
        self.assertEqual(session_start["matcher"], "startup|resume|clear|compact")
        self.assertEqual(recall_prompt["timeout"], 6)
        self.assertEqual(session_end["timeout"], 3)
        self.assertEqual(preserve["timeout"], 30)
        session_start_commands = [
            (group.get("matcher"), handler["command"], handler.get("timeout"))
            for group in hooks["hooks"]["SessionStart"]
            for handler in group["hooks"]
        ]
        session_end_commands = [
            (handler["command"], handler.get("timeout"))
            for group in hooks["hooks"]["SessionEnd"]
            for handler in group["hooks"]
        ]
        self.assertIn(
            ("startup|resume|clear", '"$HOME"/.local/bin/agent-codex-hud-launcher >/dev/null', 3),
            session_start_commands,
        )
        self.assertIn(('"$HOME"/.local/bin/agent-codex-hud-launcher --stop >/dev/null', 3), session_end_commands)
        capture = hooks["hooks"]["UserPromptSubmit"][3]["hooks"][0]
        self.assertEqual(capture["command"], '"$HOME"/.local/bin/agent-memory-hook capture')
        self.assertEqual(capture["async"], True)
        self.assertEqual(capture["timeout"], 6)

    def test_apply_preserves_unrelated_commands_in_mixed_owned_group(self) -> None:
        self.write_config("")
        self.write_hooks(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": '"/opt/custom" "unrelated"',
                                },
                                {
                                    "type": "command",
                                    "command": '"$HOME"/.local/bin/agent-memory-hook capture --async',
                                },
                            ],
                        },
                    ],
                },
            },
        )

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        hooks = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        group = hooks["hooks"]["UserPromptSubmit"][0]
        self.assertEqual(group["hooks"][0]["command"], '"/opt/custom" "unrelated"')
        self.assertEqual(group["hooks"][1]["command"], '"$HOME"/.local/bin/agent-memory-hook capture')
        self.assertEqual(group["hooks"][1]["async"], True)

    def test_apply_updates_owned_hooks_in_place(self) -> None:
        self.write_config("")
        self.write_hooks(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": '"$HOME"/.local/bin/agent-window-label old',
                                },
                            ],
                        },
                    ],
                },
            },
        )

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        hooks = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        commands = [
            handler["command"]
            for group in hooks["hooks"]["PostToolUse"]
            for handler in group["hooks"]
        ]
        self.assertEqual(commands.count('"$HOME"/.local/bin/agent-window-label ⏳ busy'), 1)
        self.assertNotIn('"$HOME"/.local/bin/agent-window-label old', commands)

    def test_unsupported_hooks_top_level_is_reported_and_removed_on_apply(self) -> None:
        self.write_config("")
        self.write_hooks({"hooks": {}, "state": {"legacy": True}})

        check = self.run_cli("--check")
        apply = self.run_cli("--apply")

        self.assertEqual(check.returncode, 1)
        self.assertIn("unsupported hooks.json top-level keys: state", check.stdout)
        self.assertEqual(apply.returncode, 2)
        self.assertIn("refusing to apply unsupported hooks.json top-level keys: state", apply.stderr)
        hooks = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("state", hooks)

    def test_apply_with_unsupported_hooks_top_level_preserves_files(self) -> None:
        self.write_config('model = "user-model"\n')
        self.write_hooks({"hooks": {}, "state": {"legacy": True}})
        before_config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        before_hooks = (self.codex_home / "hooks.json").read_text(encoding="utf-8")

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.codex_home / "config.toml").read_text(encoding="utf-8"), before_config)
        self.assertEqual((self.codex_home / "hooks.json").read_text(encoding="utf-8"), before_hooks)
        self.assertEqual(list(self.codex_home.glob("*.bak-*")), [])

    def test_apply_creates_mode_600_backups_for_existing_files(self) -> None:
        self.write_config("model = \"user-model\"\n")
        self.write_hooks({"hooks": {}})

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        backups = sorted(self.codex_home.glob("*.bak-*"))
        self.assertEqual(len(backups), 2)
        for backup in backups:
            mode = stat.S_IMODE(backup.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_invalid_config_or_hooks_json_returns_usage_error(self) -> None:
        self.write_config("[broken\n")
        self.write_hooks({"hooks": {}})
        bad_config = self.run_cli("--check")

        self.write_config("")
        (self.codex_home / "hooks.json").write_text("{broken", encoding="utf-8")
        bad_hooks = self.run_cli("--check")

        self.assertEqual(bad_config.returncode, 2)
        self.assertIn("invalid config.toml", bad_config.stderr)
        self.assertEqual(bad_hooks.returncode, 2)
        self.assertIn("invalid hooks.json", bad_hooks.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
