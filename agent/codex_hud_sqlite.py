from __future__ import annotations

import pathlib
import sqlite3
import time
from dataclasses import dataclass

from agent.codex_hud_types import ChildAgentFacts


@dataclass(frozen=True, slots=True)
class ThreadFacts:
    rollout_path: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None


def thread_facts(thread_id: str, codex_home: pathlib.Path) -> ThreadFacts:
    db = newest_state_db(codex_home)
    if db is None:
        return ThreadFacts()
    try:
        with readonly_db(db) as conn:
            row = conn.execute("SELECT rollout_path,model,reasoning_effort FROM threads WHERE id=? LIMIT 1", (thread_id,)).fetchone()
    except sqlite3.Error:
        return ThreadFacts()
    if row is None:
        return ThreadFacts()
    rollout = sqlite_text(row[0])
    if rollout is not None:
        path = pathlib.Path(rollout)
        rollout = str(path if path.is_absolute() else codex_home / path)
    return ThreadFacts(rollout, sqlite_text(row[1]), sqlite_text(row[2]))


def children_for(thread_id: str | None, codex_home: pathlib.Path) -> tuple[ChildAgentFacts, ...]:
    if thread_id is None:
        return ()
    db = newest_state_db(codex_home)
    if db is None:
        return ()
    query = "SELECT t.id,e.status,t.agent_nickname,t.agent_role,t.model,t.reasoning_effort,t.updated_at FROM thread_spawn_edges e JOIN threads t ON t.id=e.child_thread_id WHERE e.parent_thread_id=? ORDER BY t.updated_at DESC LIMIT 8"
    try:
        with readonly_db(db) as conn:
            rows = conn.execute(query, (thread_id,)).fetchall()
    except sqlite3.Error:
        return ()
    now = time.time()
    return tuple(ChildAgentFacts(str(row[0]), child_label(sqlite_text(row[2]), sqlite_text(row[3])), str(row[1]), sqlite_text(row[4]), sqlite_text(row[5]), now - float(row[6]) if isinstance(row[6], int | float) else None) for row in rows)


def newest_state_db(root: pathlib.Path) -> pathlib.Path | None:
    candidates = sorted(root.glob("state_*.sqlite"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def readonly_db(path: pathlib.Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def sqlite_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def child_label(nick: str | None, agent_role: str | None) -> str:
    if nick and agent_role:
        return f"{nick} ({agent_role})"
    return nick or agent_role or "subagent"
