#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.codex_hud_data import collect_snapshot


def write_jsonl(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def write_state(codex_home: pathlib.Path, child_status: str = "running") -> None:
    db = codex_home / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE threads ("
            "id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL, updated_at INTEGER NOT NULL,"
            "source TEXT NOT NULL, cwd TEXT NOT NULL, tokens_used INTEGER NOT NULL DEFAULT 0,"
            "agent_nickname TEXT, agent_role TEXT, model TEXT, reasoning_effort TEXT"
            ");"
            "CREATE TABLE thread_spawn_edges ("
            "parent_thread_id TEXT NOT NULL, child_thread_id TEXT NOT NULL PRIMARY KEY,"
            "status TEXT NOT NULL"
            ");"
        )
        conn.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("thread-1", "parent.jsonl", 10, "cli", "/repo", 123, None, None, "gpt-main", "high"),
        )
        conn.execute(
            "INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("child-1", "child.jsonl", 20, "spawn", "/repo", 45, "Ada", "explorer", "gpt-child", "low"),
        )
        conn.execute("INSERT INTO thread_spawn_edges VALUES (?,?,?)", ("thread-1", "child-1", child_status))


class CodexHudData(unittest.TestCase):
    def test_exact_session_snapshot_uses_only_pane_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            codex_home = tmp / "codex"
            codex_home.mkdir()
            transcript = codex_home / "sessions" / "rollout-thread-1.jsonl"
            stale = codex_home / "sessions" / "rollout-stale.jsonl"
            write_jsonl(
                transcript,
                [
                    {"type": "session_meta", "timestamp": "2026-09-07T00:00:00Z", "payload": {"id": "thread-1", "model": "gpt-5.5", "reasoning_effort": "high", "context_window": 1000}},
                    {"type": "turn_context", "timestamp": "2026-09-07T00:00:01Z", "payload": {"model": "gpt-5.5", "effort": "high"}},
                    {"type": "response_item", "timestamp": "2026-09-07T00:00:02Z", "payload": {"type": "function_call", "name": "shell.exec"}},
                    {"type": "event_msg", "timestamp": "2026-09-07T00:00:03Z", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 200, "cached_input_tokens": 80, "cache_write_input_tokens": 20, "output_tokens": 50, "reasoning_output_tokens": 5, "total_tokens": 250}, "last_token_usage": {"input_tokens": 80, "cached_input_tokens": 20, "output_tokens": 20, "total_tokens": 100}, "model_context_window": 1000}, "rate_limits": {"primary": {"used_percent": 12.5, "window_minutes": 300, "resets_at": 1788779999}, "secondary": {"used_percent": 30.0, "window_minutes": 10080}}}},
                ],
            )
            write_jsonl(stale, [{"type": "session_meta", "payload": {"id": "newest"}}, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 999999}, "model_context_window": 1000000}}}])
            write_state(codex_home)
            hud = tmp / "tmux"
            hud.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {codex_home};; esac\n", encoding="utf-8")
            hud.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.thread_id, "thread-1")
            self.assertEqual(snapshot.session.model, "gpt-5.5")
            self.assertEqual(snapshot.usage.total_tokens, 250)
            self.assertEqual(snapshot.usage.cache_ratio_percent, 40.0)
            self.assertEqual(snapshot.context.used_percent, 10.0)
            self.assertEqual(snapshot.limits.primary_used_percent, 12.5)
            self.assertEqual(snapshot.limits.weekly_used_percent, 30.0)
            self.assertEqual(snapshot.children[0].label, "Ada (explorer)")
            self.assertEqual(snapshot.recent_tool.name, "shell.exec")
            self.assertEqual(snapshot.tasks.status, "unavailable")

    def test_missing_pane_session_does_not_choose_newest_cwd_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            codex_home = tmp / "codex"
            write_jsonl(codex_home / "sessions" / "rollout-newest.jsonl", [{"type": "session_meta", "payload": {"id": "newest"}}, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 999}, "model_context_window": 1000}}}])
            os.environ["CODEX_HOME"] = str(codex_home)
            try:
                snapshot = collect_snapshot(None, REPO)
            finally:
                os.environ.pop("CODEX_HOME", None)
            self.assertEqual(snapshot.session.status, "unknown")
            self.assertIsNone(snapshot.usage.total_tokens)

    def test_exact_session_can_use_sqlite_rollout_when_transcript_option_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            codex_home = tmp / "codex"
            codex_home.mkdir()
            write_state(codex_home)
            fresh = datetime.now(UTC).isoformat()
            rows = [
                json.dumps({"type": "session_meta", "payload": {"id": "thread-1"}}),
                json.dumps({"type": "turn_context", "payload": {"model": "tail-missed", "effort": "tail-missed", "pad": "x" * 600_000}}),
                json.dumps({"type": "event_msg", "timestamp": fresh, "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 321}, "last_token_usage": {"total_tokens": 21}, "model_context_window": 1000}}}),
            ]
            (codex_home / "parent.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_home'*) printf {codex_home};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.status, "ready")
            self.assertEqual(snapshot.session.model, "gpt-main")
            self.assertEqual(snapshot.session.reasoning_effort, "high")
            self.assertEqual(snapshot.usage.total_tokens, 321)
            self.assertLess(snapshot.session.updated_age_seconds or 99.0, 10.0)

    def test_mismatched_transcript_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-other.jsonl"
            write_jsonl(transcript, [{"type": "session_meta", "payload": {"id": "other-thread"}}, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 999}, "model_context_window": 1000}}}])
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.status, "malformed")
            self.assertIsNone(snapshot.usage.total_tokens)

    def test_omx_status_requires_exact_session_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-thread-1.jsonl"
            write_jsonl(transcript, [{"type": "session_meta", "payload": {"id": "thread-1"}}])
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            omx = tmp / "omx"
            omx.write_text(f"#!/bin/sh\nprintf '%s\\n' '{{\"session\":{{\"session_id\":\"other\",\"cwd\":\"{REPO}\"}},\"team\":{{\"workers\":3}}}}'\n", encoding="utf-8")
            tmux.chmod(0o755)
            omx.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.omx.status, "unavailable")
            self.assertEqual(snapshot.omx.workflows, ())

    def test_active_transcript_ignores_incomplete_final_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-thread-1.jsonl"
            transcript.write_text(
                json.dumps({"type": "session_meta", "payload": {"id": "thread-1", "model_provider": "openai"}})
                + "\n"
                + json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.5"}})
                + "\n"
                + json.dumps({"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "CommandExecution", "command": ["/bin/sh", "-lc", "secret=1"]}}})
                + "\n"
                + '{"type":"event_msg"',
                encoding="utf-8",
            )
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.status, "ready")
            self.assertEqual(snapshot.session.model, "gpt-5.5")
            self.assertEqual(snapshot.recent_tool.name, "CommandExecution")

    def test_malformed_transcript_keeps_live_memory_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "bad.jsonl"
            transcript.write_text("{bad json\n", encoding="utf-8")
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_session'*) printf thread-1;; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            os.environ["AGMEM_DAEMON_URL"] = "http://127.0.0.1:9"
            os.environ["AGMEM_HOOK"] = str(tmp / "missing-memory-hook")
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
                os.environ.pop("AGMEM_DAEMON_URL", None)
                os.environ.pop("AGMEM_HOOK", None)
            self.assertEqual(snapshot.session.status, "malformed")
            self.assertEqual(snapshot.memory.health, "down")
            self.assertEqual(snapshot.memory.recall, "unavailable")

    def test_transcript_without_bound_session_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-thread-1.jsonl"
            write_jsonl(transcript, [{"type": "session_meta", "payload": {"id": "thread-1"}}, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 999}, "last_token_usage": {"total_tokens": 9}, "model_context_window": 100}}}])
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.status, "unknown")
            self.assertIsNone(snapshot.usage.total_tokens)

    def test_context_percent_is_unknown_without_last_token_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-thread-1.jsonl"
            write_jsonl(transcript, [{"type": "session_meta", "payload": {"id": "thread-1"}}, {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 900}, "model_context_window": 1000}}}])
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            tmux.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.usage.total_tokens, 900)
            self.assertIsNone(snapshot.context.used_percent)

    def test_non_object_json_boundaries_do_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_raw:
            tmp = pathlib.Path(tmp_raw)
            transcript = tmp / "rollout-thread-1.jsonl"
            transcript.write_text("[]\n", encoding="utf-8")
            tmux = tmp / "tmux"
            tmux.write_text(f"#!/bin/sh\ncase \"$*\" in *'@codex_hud_session'*) printf thread-1;; *'@codex_hud_transcript'*) printf {transcript};; *'@codex_hud_home'*) printf {tmp};; esac\n", encoding="utf-8")
            omx = tmp / "omx"
            omx.write_text("#!/bin/sh\nprintf '[]\\n'\n", encoding="utf-8")
            tmux.chmod(0o755)
            omx.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{tmp}{os.pathsep}{old_path}"
            try:
                snapshot = collect_snapshot("%1", REPO)
            finally:
                os.environ["PATH"] = old_path
            self.assertEqual(snapshot.session.status, "malformed")
            self.assertEqual(snapshot.omx.status, "unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=1)
