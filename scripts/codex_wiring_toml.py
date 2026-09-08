#!/usr/bin/env python3
from __future__ import annotations

import pathlib
from typing import Final, Literal

import tomllib

from .codex_wiring_hooks import omx_stop_hook_state_key

STATUS_LINE: Final = [
    "context-remaining",
    "five-hour-limit",
    "weekly-limit",
    "used-tokens",
    "estimated-thread-cost",
    "git-branch",
]
AGMEM_URL: Final = "http://127.0.0.1:8765/mcp"
WORKFLOW_OMO_HOOKS: Final = (
    "user-prompt-submit-checking-ultrawork-trigger",
    "user-prompt-submit-checking-ulw-loop-steering",
    "pre-tool-use-enforcing-unlimited-goal-budget",
    "pre-tool-use-guarding-ulw-loop-spawns",
    "stop-checking-start-work-continuation",
    "stop-checking-ulw-loop-resume",
    "subagent-stop-checking-start-work-continuation",
    "subagent-stop-verifying-lazycodex-executor-evidence",
)


def render_config(config_text: str, workflow_owner: Literal["omx"] | None, codex_home: pathlib.Path, hooks_text: str) -> str:
    unsupported = unsupported_toml_shape(config_text)
    if unsupported is not None:
        raise RuntimeError(f"unsupported config.toml shape: {unsupported}")
    rendered = replace_mcp(replace_status_line(config_text))
    if workflow_owner == "omx":
        rendered = apply_omx_workflow_owner(rendered, codex_home, hooks_text)
    tomllib.loads(rendered)
    return rendered


def unsupported_toml_shape(config_text: str) -> str | None:
    if '"""' in config_text or "'''" in config_text:
        return "multiline strings are not supported by this comment-preserving editor"
    return None


def replace_status_line(config_text: str) -> str:
    lines = config_text.splitlines()
    tui_start = find_table(lines, "tui")
    if tui_start is None:
        prefix = config_text.rstrip("\n")
        separator = "\n\n" if prefix else ""
        return f"{prefix}{separator}[tui]\n# codex-wiring: managed status line\n{status_line_toml()}\n"
    end = find_next_table(lines, tui_start + 1) or len(lines)
    new_lines = lines[:]
    status_start = find_key_in_range(new_lines, "status_line", tui_start + 1, end)
    if status_start is None:
        new_lines.insert(tui_start + 1, status_line_toml())
    else:
        new_lines[status_start:find_value_end(new_lines, status_start)] = [status_line_toml()]
    return "\n".join(new_lines) + "\n"


def replace_mcp(config_text: str) -> str:
    lines = config_text.splitlines()
    start = find_table(lines, "mcp_servers.agentic_memory")
    if start is None:
        prefix = config_text.rstrip("\n")
        separator = "\n\n" if prefix else ""
        return f"{prefix}{separator}" + "\n".join(mcp_lines()) + "\n"
    end = find_next_table(lines, start + 1) or len(lines)
    new_lines = lines[:]
    for key, value in (
        ("url", f'"{AGMEM_URL}"'),
        ("startup_timeout_sec", "30"),
        ("tool_timeout_sec", "60"),
        ("required", "false"),
    ):
        new_lines = upsert_key_in_table(new_lines, start, end, key, value)
        end = find_next_table(new_lines, start + 1) or len(new_lines)
    return "\n".join(new_lines) + "\n"


def apply_omx_workflow_owner(config_text: str, codex_home: pathlib.Path, hooks_text: str) -> str:
    out = config_text.splitlines()
    for name in WORKFLOW_OMO_HOOKS:
        out = set_existing_state_enabled(out, f'hooks.state."omo@sisyphuslabs:hooks/{name}.json:', "false")
    stop_key = omx_stop_hook_state_key(hooks_text, codex_home / "hooks.json")
    if stop_key is not None:
        out = upsert_state_enabled(out, stop_key, "true")
    return "\n".join(out) + "\n"


def set_existing_state_enabled(lines: list[str], table_prefix: str, value: str) -> list[str]:
    out = lines[:]
    indexes = [
        index
        for index, line in enumerate(lines)
        if (name := table_name(line)) is not None and name.startswith(table_prefix)
    ]
    for index in reversed(indexes):
        out = upsert_key_in_table(out, index, find_next_table(out, index + 1) or len(out), "enabled", value)
    return out


def upsert_state_enabled(lines: list[str], table: str, value: str) -> list[str]:
    start = find_table(lines, table)
    if start is None:
        return [*lines, "", f"[{table}]", f"enabled = {value}"]
    return upsert_key_in_table(lines, start, find_next_table(lines, start + 1) or len(lines), "enabled", value)


def status_line_toml() -> str:
    values = ", ".join(f'"{item}"' for item in STATUS_LINE)
    return f"status_line = [{values}]"


def mcp_lines() -> list[str]:
    return [
        "[mcp_servers.agentic_memory]",
        f'url = "{AGMEM_URL}"',
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 60",
        "required = false",
    ]


def table_name(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped.strip("[]")
    return None


def find_table(lines: list[str], name: str) -> int | None:
    for index, line in enumerate(lines):
        if table_name(line) == name:
            return index
    return None


def find_next_table(lines: list[str], start: int) -> int | None:
    for index in range(start, len(lines)):
        if table_name(lines[index]) is not None:
            return index
    return None


def find_key_in_range(lines: list[str], key: str, start: int, end: int) -> int | None:
    for index in range(start, end):
        stripped = lines[index].lstrip()
        if stripped.startswith((f"{key}=", f"{key} ")):
            return index
    return None


def find_value_end(lines: list[str], start: int) -> int:
    balance = lines[start].count("[") - lines[start].count("]")
    index = start + 1
    while balance > 0 and index < len(lines):
        balance += lines[index].count("[") - lines[index].count("]")
        index += 1
    return index


def upsert_key_in_table(lines: list[str], start: int, end: int, key: str, value: str) -> list[str]:
    found = find_key_in_range(lines, key, start + 1, end)
    new_lines = lines[:]
    if found is None:
        insert_at = end
        while insert_at > start + 1 and new_lines[insert_at - 1].strip() == "":
            insert_at -= 1
        new_lines.insert(insert_at, f"{key} = {value}")
        return new_lines
    new_lines[found:find_value_end(new_lines, found)] = [f"{key} = {value}"]
    return new_lines
