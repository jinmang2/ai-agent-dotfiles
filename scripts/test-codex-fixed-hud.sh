#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
socket="hud-fixed-$$"
trap 'tmux -L "$socket" kill-server 2>/dev/null || true' EXIT
tmux -L "$socket" -f /dev/null new-session -d -s lifecycle -x 100 -y 24
parent=$(tmux -L "$socket" display-message -p -t lifecycle '#{pane_id}')
export TMUX="$(tmux -L "$socket" display-message -p '#{socket_path}'),0,0"
export TMUX_PANE="$parent"
unset CODEX_COMPANION_HUD_ACTIVE
launcher="$repo/agent/codex-hud-launcher"
tabs=$(tmux show-option -gqv 'status-format[0]')

# Given an opted-out pane, when launched, then no registration appears.
CODEX_HUD=0 "$launcher" </dev/null
[ "$(tmux list-panes -t lifecycle | wc -l)" -eq 1 ]
[ -z "$(tmux show-option -pqv -t "$parent" @codex_hud_active)" ]

# Given a normal parent, when launched twice, then only a fixed row is installed.
"$launcher" </dev/null
"$launcher" </dev/null
[ "$(tmux list-panes -t lifecycle | wc -l)" -eq 1 ] || { echo 'FAIL: HUD must not split a pane'; exit 1; }
[ "$(tmux show-option -pqv -t "$parent" @codex_hud_active)" = 1 ]
[ "$(tmux show-option -gqv 'status-format[1]')" = "$tabs" ]

# Given an exact native session, when registered, then its identity is pane-local.
printf '%s' '{"session_id":"11111111-1111-4111-8111-111111111111","transcript_path":"/tmp/hud-test.jsonl"}' | "$launcher"
[ "$(tmux show-option -pqv -t "$parent" @codex_hud_session)" = 11111111-1111-4111-8111-111111111111 ]
other=$(tmux new-window -d -P -F '#{pane_id}' -t lifecycle)
[ -z "$(tmux show-option -pqv -t "$other" @codex_hud_session)" ]
tmux select-window -t "$other"
"$launcher" --refresh --pane "$other"
[ "$(tmux show-option -qv -t lifecycle status)" = on ]
tmux select-window -t "$parent"
"$launcher" --refresh --pane "$parent"
[ "$(tmux show-option -qv -t lifecycle status)" = 2 ]
printf '%s' '{"session_id":"22222222-2222-4222-8222-222222222222"}' | "$launcher" --stop
[ "$(tmux show-option -pqv -t "$parent" @codex_hud_active)" = 1 ]

# Given an obsolete owned HUD, when registration repeats, then only it is removed.
legacy=$(tmux split-window -d -P -F '#{pane_id}' -t "$parent")
tmux set-option -pq -t "$legacy" @codex_hud_parent "$parent"
tmux set-option -gq "@codex_hud_pane_${parent//[^A-Za-z0-9]/_}" "$legacy"
"$launcher" </dev/null
[ "$(tmux list-panes -t "$parent" | wc -l)" -eq 1 ]

# Given an unrelated pane in a stale pointer, when stopped, then it survives.
tmux set-option -gq "@codex_hud_pane_${parent//[^A-Za-z0-9]/_}" "$other"
"$launcher" --stop </dev/null
tmux display-message -p -t "$other" '#{pane_id}' >/dev/null
[ -z "$(tmux show-option -pqv -t "$parent" @codex_hud_session)" ]
"$launcher" --stop </dev/null
TMUX_PANE= "$launcher" </dev/null
echo 'Fixed HUD lifecycle: no split, tab preservation, session isolation, legacy cleanup, stop passed'
