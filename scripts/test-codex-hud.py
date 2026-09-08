#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import override

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.codex_hud_render import render_detail, render_status, render_status_plain
from agent.codex_hud_types import (
    ChildAgentFacts,
    ContextFacts,
    LimitFacts,
    MemoryFacts,
    OmxFacts,
    SessionFacts,
    Snapshot,
    TaskFacts,
    ToolFacts,
    UsageTotals,
)

HUD = REPO / "agent" / "codex-hud.py"


def plain_status(text: str) -> str:
    return re.sub(r"#\[[^]]*\]", "", text)


def plain_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def display_width(text: str) -> int:
    total = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return total


def snapshot() -> Snapshot:
    return Snapshot(
        SessionFacts("ready", "thread-1", "/tmp/rollout.jsonl", "gpt-5.5", "high", 3),
        UsageTotals(200, 50, 80, 20, 5, 250, 40.0),
        ContextFacts(1000, 25.0),
        LimitFacts(12.5, 300, 1788779999, 30.0),
        (ChildAgentFacts("child-1", "Ada (explorer)", "running", "gpt-child", "low", 20),),
        ToolFacts("#[bad]shell\n.exec", 9),
        MemoryFacts("ready", "available", "available"),
        OmxFacts("active", ("team",), ("turns 4",)),
        TaskFacts("available", 1, 2),
        ("pane", "/tmp/rollout.jsonl"),
    )


def run_hud(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(HUD), *args], cwd=REPO, capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False)


class CodexHud(unittest.TestCase):
    def test_status_is_one_tmux_line_prioritizing_context_limits(self) -> None:
        result = render_status(snapshot(), 220)
        plain = plain_status(result)
        self.assertNotIn("\n", result)
        self.assertLess(plain.find("ctx 75% left"), plain.find("session ready"))
        self.assertLess(plain.find("5h 12% used"), plain.find("tok 250"))
        self.assertIn("week 30% used", plain)
        self.assertIn("agents 1 shown", plain)
        self.assertIn("tasks 1/2", plain)
        self.assertIn("obs 3s ago", plain)
        self.assertIn("obs 3s ago", plain_status(render_status(snapshot(), 60)))

    def test_status_sanitizes_tmux_ansi_control_and_newlines(self) -> None:
        dirty = Snapshot(
            SessionFacts("ready"),
            UsageTotals(),
            ContextFacts(),
            LimitFacts(),
            (),
            ToolFacts("#[bad]shell\n.exec\033[31m", 9),
            MemoryFacts("ready", "unavailable", "unavailable"),
            OmxFacts(),
            TaskFacts(),
            (),
        )
        result = render_status(dirty, 80)
        self.assertNotIn("#[bad]", result)
        self.assertIn("[bad]shell .exec", result)
        self.assertNotIn("\033", result)
        self.assertNotIn("\n", result)

    def test_once_plain_output_does_not_emit_tmux_markup(self) -> None:
        result = render_status_plain(snapshot(), 160, False)
        self.assertNotIn("#[", result)
        self.assertNotIn("\033", result)
        self.assertIn("ctx 75% left", result)

    def test_status_width_progressively_omits_lower_priority_fields(self) -> None:
        for width in (8, 16, 24, 40):
            with self.subTest(width=width):
                line = plain_status(render_status(snapshot(), width))
                self.assertLessEqual(display_width(line), width)
        self.assertIn("ctx", plain_status(render_status(snapshot(), 16)))
        self.assertNotIn("agents", plain_status(render_status(snapshot(), 24)))

    def test_detail_reports_rich_snapshot_plainly(self) -> None:
        detail = plain_ansi(render_detail(snapshot()))
        self.assertIn("Usage\ncontext remaining  75%", detail)
        self.assertIn("context used       25%", detail)
        self.assertIn("weekly limit       30% used", detail)
        self.assertIn("cache hit          40%", detail)
        self.assertIn("Activity\n - Ada (explorer) / edge:running / gpt-child / low", detail)
        self.assertRegex(detail, r"tasks\s+1/2 \(available\)")
        self.assertRegex(detail, r"memory\s+ready/recall:observed/save:observed")
        self.assertRegex(detail, r"Metadata\nsession\s+thread-1")
        self.assertRegex(detail, r"sources\s+pane, /tmp/rollout\.jsonl")
        self.assertNotIn("#[", detail)

    def test_open_child_edges_are_not_reported_as_runtime_status(self) -> None:
        children = tuple(
            ChildAgentFacts(f"child-{index}", f"agent-{index}", "open", None, None, None)
            for index in range(8)
        )
        snap = Snapshot(
            SessionFacts("ready"),
            UsageTotals(),
            ContextFacts(),
            LimitFacts(50.0, 60, None, None),
            children,
            ToolFacts(),
            MemoryFacts("ready", "unavailable", "unavailable"),
            OmxFacts(),
            TaskFacts(),
            (),
        )
        status = plain_status(render_status(snap, 120))
        detail = plain_ansi(render_detail(snap, False))
        self.assertIn("agents 8 shown", status)
        self.assertNotIn("agents 0/8", status)
        self.assertIn(" - agent-0 / edge:open", detail)
        self.assertRegex(detail, r"limit/primary limit\s+50% used")
        self.assertNotIn("5h/primary limit", detail)

    def test_cli_json_uses_typed_collector_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout.jsonl"
            transcript.write_text(
                "\n".join(
                    (
                        json.dumps({"type": "session_meta", "timestamp": "2026-09-07T00:00:00Z", "payload": {"id": "thread-1", "model": "gpt-5.5", "reasoning_effort": "high"}}),
                        json.dumps({"type": "event_msg", "timestamp": "2026-09-07T00:00:01Z", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 200, "cached_input_tokens": 80, "output_tokens": 50, "total_tokens": 250}, "last_token_usage": {"total_tokens": 250}, "model_context_window": 1000}, "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 300}, "secondary": {"used_percent": 20, "window_minutes": 10080}}}}),
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            server, env = self.health_env(tmp)
            try:
                result = run_hud("--json", "--pane", "%1", env={**env, "PATH": f"{tmp}{os.pathsep}{os.environ.get('PATH', '')}"})
            finally:
                server.shutdown()
                server.server_close()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["session"]["thread_id"], "thread-1")
        self.assertEqual(payload["usage"]["total_tokens"], 250)
        self.assertEqual(payload["context"]["used_percent"], 25.0)
        self.assertIn("tasks", payload)

    def test_cli_status_and_detail_do_not_report_unknown_usage_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            empty_path = pathlib.Path(tmp_raw) / "bin"
            empty_path.mkdir()
            env = {"PATH": str(empty_path), "AGMEM_DAEMON_URL": "http://127.0.0.1:9"}
            result = run_hud("--status", "--pane", "%9", "--width", "100", env=env)
            detail = run_hud("--detail", "--pane", "%9", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("tok 0", plain_status(result.stdout))
        self.assertEqual(detail.returncode, 0, detail.stderr)
        self.assertRegex(plain_ansi(detail.stdout), r"transcript\s+unknown")
        self.assertNotIn("used tokens: 0", detail.stdout)

    def test_cli_no_color_removes_detail_ansi_and_once_tmux_markup(self) -> None:
        result = run_hud("--once", "--no-color", "--width", "100", env={"AGMEM_DAEMON_URL": "http://127.0.0.1:9"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("#[", result.stdout)
        self.assertNotIn("\033", result.stdout)
        detail = run_hud("--detail", "--no-color", env={"AGMEM_DAEMON_URL": "http://127.0.0.1:9"})
        self.assertEqual(detail.returncode, 0, detail.stderr)
        self.assertNotIn("\033", detail.stdout)

    def test_help_lists_status_detail_and_pane_contract(self) -> None:
        result = run_hud("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--status", result.stdout)
        self.assertIn("--detail", result.stdout)
        self.assertIn("--pane", result.stdout)

    def health_env(self, tmp: pathlib.Path) -> tuple[HTTPServer, dict[str, str]]:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            @override
            def log_message(self, format: str, *args: str) -> None:
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        address = server.server_address
        if len(address) != 2:
            raise TypeError("unexpected server address")
        host = address[0]
        port = address[1]
        if not isinstance(host, str):
            raise TypeError("unexpected server address")
        return server, {"AGMEM_DAEMON_URL": f"http://{host}:{port}", "AGMEM_HOOK": str(tmp / "memory-hook")}


if __name__ == "__main__":
    unittest.main(verbosity=1)
