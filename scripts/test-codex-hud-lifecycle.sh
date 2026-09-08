#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
socket="hud-lifecycle-$$"
cleanup() {
  tmux -L "$socket" kill-server 2>/dev/null || true
}
trap cleanup EXIT
tmux -L "$socket" -f /dev/null new-session -d -s lifecycle -x 100 -y 24
parent=$(tmux -L "$socket" display-message -p -t lifecycle '#{pane_id}')
export TMUX="$(tmux -L "$socket" display-message -p '#{socket_path}'),0,0"
export TMUX_PANE="$parent"
unset CODEX_COMPANION_HUD_ACTIVE
export CODEX_HUD=0
result=$("$repo/agent/codex-hud-launcher")
[ -z "$result" ] || { echo 'FAIL: CODEX_HUD=0 launched a pane'; exit 1; }
export CODEX_HUD=1
first=$("$repo/agent/codex-hud-launcher")
second=$("$repo/agent/codex-hud-launcher")
[ "$first" = "$second" ]
[ "$(tmux list-panes -t lifecycle -F '#{pane_id}' | wc -l)" -eq 1 ]
[ "$(tmux show-option -pqv -t "$parent" @codex_hud_active)" = 1 ]
"$repo/agent/codex-hud-launcher" --stop
[ "$(tmux list-panes -t lifecycle -F '#{pane_id}' | wc -l)" -eq 1 ]
"$repo/agent/codex-hud-launcher" --stop
third=$("$repo/agent/codex-hud-launcher")
[ -z "$third" ]
[ "$(tmux show-option -pqv -t "$parent" @codex_hud_active)" = 1 ]
"$repo/agent/codex-hud-launcher" --stop
TMUX_PANE= "$repo/agent/codex-hud-launcher" >/dev/null
tmux set-option -gq "@codex_hud_pane_${parent//[^A-Za-z0-9]/_}" "$parent"
"$repo/agent/codex-hud-launcher" --stop
tmux display-message -p -t "$parent" '#{pane_id}' >/dev/null
echo 'HUD lifecycle: opt-out, idempotent start, stop, re-entry, outside-tmux passed'
