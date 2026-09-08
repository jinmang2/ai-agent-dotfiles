#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
from typing import Final, TypedDict

REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[1]
HOOKS_SNIPPET: Final = REPO_ROOT / "codex" / "hooks.snippet.json"
LEGACY_CAPTURE_COMMAND: Final = '"$HOME"/.local/bin/agent-memory-hook capture --async'
ALLOWED_HOOKS_TOP_LEVEL: Final = {"description", "hooks"}

HookCommand = TypedDict(
    "HookCommand",
    {"type": str, "command": str, "timeout": int, "statusMessage": str, "async": bool},
    total=False,
)


class HookGroup(TypedDict, total=False):
    matcher: str
    hooks: list[HookCommand]


class HooksFile(TypedDict, total=False):
    description: str
    hooks: dict[str, list[HookGroup]]


def hook_specs() -> dict[str, list[HookGroup]]:
    snippet = json.loads(HOOKS_SNIPPET.read_text(encoding="utf-8"))
    if not isinstance(snippet, dict):
        raise TypeError("hooks snippet must be an object")
    specs: dict[str, list[HookGroup]] = {}
    for event, value in snippet.items():
        if event == "_comment":
            continue
        if not isinstance(value, list):
            raise TypeError(f"hooks snippet {event} must be an array")
        specs[str(event)] = value
    return specs


def parse_hooks(raw: str) -> tuple[HooksFile, tuple[str, ...]]:
    parsed = json.loads(raw) if raw.strip() else {}
    if not isinstance(parsed, dict):
        raise TypeError("hooks.json must be an object")
    unsupported = tuple(sorted(str(key) for key in parsed if key not in ALLOWED_HOOKS_TOP_LEVEL))
    hooks = parsed.get("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("hooks.json hooks must be an object")
    out: HooksFile = {"hooks": hooks}
    description = parsed.get("description")
    if isinstance(description, str):
        out["description"] = description
    return out, unsupported


def render_hooks(raw: str) -> tuple[str, tuple[str, ...]]:
    parsed, unsupported = parse_hooks(raw)
    hooks = parsed.setdefault("hooks", {})
    for event, expected_groups in hook_specs().items():
        groups = hooks.setdefault(event, [])
        for expected in expected_groups:
            merge_hook_group(groups, expected)
    return json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", unsupported


def merge_hook_group(groups: list[HookGroup], replacement: HookGroup) -> None:
    expected = first_command(replacement)
    for index, group in enumerate(groups):
        command_index = matching_command_index(group, expected)
        if command_index is None:
            continue
        hooks = group.get("hooks", [])
        if len(hooks) == 1:
            groups[index] = replacement
            return
        hooks[command_index] = first_hook(replacement)
        return
    groups.append(replacement)


def first_hook(group: HookGroup) -> HookCommand:
    hooks = group.get("hooks", [])
    if not hooks:
        raise TypeError("managed hook group must contain a command")
    return hooks[0]


def first_command(group: HookGroup) -> str:
    command = first_hook(group).get("command")
    if not isinstance(command, str):
        raise TypeError("managed hook command must be a string")
    return command


def matching_command_index(group: HookGroup, expected: str) -> int | None:
    for index, command in enumerate(group.get("hooks", [])):
        current = command.get("command", "")
        if current == expected:
            return index
        if expected.endswith("agent-memory-hook capture") and current == LEGACY_CAPTURE_COMMAND:
            return index
        if "agent-window-label" in expected and "agent-window-label" in current:
            return index
    return None


def omx_stop_hook_state_key(hooks_text: str, hooks_path: pathlib.Path) -> str | None:
    parsed, _unsupported = parse_hooks(hooks_text)
    stop_groups = parsed.get("hooks", {}).get("Stop", [])
    for group_index, group in enumerate(stop_groups):
        for command_index, command in enumerate(group.get("hooks", [])):
            if "codex-native-hook.js" in command.get("command", ""):
                return f'hooks.state."{hooks_path}:stop:{group_index}:{command_index}"'
    return None
