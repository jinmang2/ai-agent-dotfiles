#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "codex-wiring.py"
type JsonValue = str | int | bool | None | list[JsonValue] | dict[str, JsonValue]


class CodexWiringWorkflow(unittest.TestCase):
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

    def test_valid_but_unsupported_toml_shape_is_refused(self) -> None:
        self.write_config('notes = """[not.a.table]"""\n')
        self.write_hooks({"hooks": {}})

        result = self.run_cli("--check")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unsupported config.toml shape", result.stderr)

    def test_check_with_unsupported_hooks_top_level_renders_desired_diff(self) -> None:
        self.write_config("")
        self.write_hooks({"hooks": {}, "state": {"legacy": True}})

        check = self.run_cli("--check")

        self.assertEqual(check.returncode, 1)
        self.assertIn("would update hooks.json", check.stdout)
        hooks = json.loads((self.codex_home / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("state", hooks)

    def test_workflow_owner_omx_toggles_only_supported_hook_state(self) -> None:
        self.write_config(
            '[hooks.state."omo@sisyphuslabs:hooks/user-prompt-submit-checking-ultrawork-trigger.json:user_prompt_submit:0:0"]\n'
            'trusted_hash = "sha256:workflow"\n'
            '\n'
            '[hooks.state."omo@sisyphuslabs:hooks/post-tool-use-checking-lsp-diagnostics.json:post_tool_use:0:0"]\n'
            'trusted_hash = "sha256:diagnostics"\n'
            'enabled = true\n'
            '\n'
        )
        self.write_hooks(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": '"/opt/node" "/opt/omx/codex-native-hook.js"',
                                },
                            ],
                        },
                    ],
                },
            },
        )

        result = self.run_cli("--apply", "--workflow-owner", "omx")

        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('trusted_hash = "sha256:workflow"\nenabled = false', config)
        self.assertIn('trusted_hash = "sha256:diagnostics"\nenabled = true', config)
        self.assertIn(f'[hooks.state."{self.codex_home / "hooks.json"}:stop:0:0"]\nenabled = true', config)

    def test_workflow_owner_omx_enables_stop_group_zero_command_one_only(self) -> None:
        self.write_config(
            f'[hooks.state."{self.codex_home / "hooks.json"}:stop:0:0"]\n'
            'trusted_hash = "sha256:unrelated"\n'
            'enabled = false\n'
            '\n'
            f'[hooks.state."{self.codex_home / "hooks.json"}:stop:0:1"]\n'
            'trusted_hash = "sha256:omx"\n'
            'enabled = false\n'
            '\n'
        )
        self.write_hooks(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": '"/opt/custom" "unrelated"'},
                                {"type": "command", "command": '"/opt/node" "/opt/omx/codex-native-hook.js"'},
                            ],
                        },
                    ],
                },
            },
        )

        result = self.run_cli("--apply", "--workflow-owner", "omx")

        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('trusted_hash = "sha256:unrelated"\nenabled = false', config)
        self.assertIn('trusted_hash = "sha256:omx"\nenabled = true', config)

    def test_workflow_owner_omx_enables_stop_group_one_command_zero_only(self) -> None:
        self.write_config(
            f'[hooks.state."{self.codex_home / "hooks.json"}:stop:0:0"]\n'
            'trusted_hash = "sha256:unrelated"\n'
            'enabled = false\n'
            '\n'
            f'[hooks.state."{self.codex_home / "hooks.json"}:stop:1:0"]\n'
            'trusted_hash = "sha256:omx"\n'
            'enabled = false\n'
            '\n'
        )
        self.write_hooks(
            {
                "hooks": {
                    "Stop": [
                        {"hooks": [{"type": "command", "command": '"/opt/custom" "unrelated"'}]},
                        {"hooks": [{"type": "command", "command": '"/opt/node" "/opt/omx/codex-native-hook.js"'}]},
                    ],
                },
            },
        )

        result = self.run_cli("--apply", "--workflow-owner", "omx")

        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('trusted_hash = "sha256:unrelated"\nenabled = false', config)
        self.assertIn('trusted_hash = "sha256:omx"\nenabled = true', config)

    def test_workflow_owner_omx_updates_two_matching_tables_without_enabled(self) -> None:
        self.write_config(
            '[hooks.state."omo@sisyphuslabs:hooks/user-prompt-submit-checking-ultrawork-trigger.json:user_prompt_submit:0:0"]\n'
            'trusted_hash = "sha256:first"\n'
            '\n'
            '[hooks.state."omo@sisyphuslabs:hooks/stop-checking-ulw-loop-resume.json:stop:0:0"]\n'
            'trusted_hash = "sha256:second"\n'
            '\n'
        )
        self.write_hooks({"hooks": {}})

        result = self.run_cli("--apply", "--workflow-owner", "omx")

        self.assertEqual(result.returncode, 0, result.stderr)
        config = (self.codex_home / "config.toml").read_text(encoding="utf-8")
        self.assertIn('trusted_hash = "sha256:first"\nenabled = false', config)
        self.assertIn('trusted_hash = "sha256:second"\nenabled = false', config)


if __name__ == "__main__":
    unittest.main(verbosity=1)
