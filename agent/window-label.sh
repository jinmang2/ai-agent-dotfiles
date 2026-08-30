#!/usr/bin/env bash
# tmux 창 이름을 "<상태><프로필마커><라벨>" 로 갱신한다.
# Claude Code 와 Codex 양쪽 훅에서 그대로 호출된다.
#   $1 = 상태 이모지 (⏳ 작업중 / ❓ 입력대기 / ✅ 완료).  빈 값이면 @cc 에서 유추.
#   $2 = @cc 에 기록할 상태 문자열 (busy/waiting/done). 빈 값이면 건드리지 않음.
#
# 프로필 마커: $AGENT_PROFILE 을 profiles.conf 에서 조회.
#   AGENT_PROFILE 이 없으면 $CLAUDE_CONFIG_DIR 에서 유도한다 (.claude-team -> claude-team).
#   두 변수가 어긋나면 창 마커와 HUD 의 profile: 이 서로 다른 계정을 가리키게 되는데,
#   실제로 그런 창이 나왔다 — CLAUDE_CONFIG_DIR 만 걸린 채 실행된 세션이 team 계정을
#   쓰면서 창에는 🔵(개인) 마커를 달고 있었다.  HUD 도 같은 값을 보므로 유도가 맞다.
#   Claude Code 와 Codex 가 같은 스크립트를 공유한다 (훅 형식이 동일).
# 라벨 우선순위: @cc_label(수동 작업명) > agent/label-of.sh 의 규칙
#   라벨 규칙 자체는 셸(shell/agents.sh)과 나눠 갖는 한 벌이다 — label-of.sh.
set -u

CONF="${AGENT_PROFILES_CONF:-$HOME/.config/agent-profiles.conf}"
LABEL_LIB="${AGENT_LABEL_LIB:-$HOME/.config/agent-dotfiles/label-of.sh}"

emoji="${1:-}"
state="${2:-}"

[ -n "${TMUX_PANE:-}" ] || exit 0
command -v tmux >/dev/null 2>&1 || exit 0

payload=$(cat 2>/dev/null)

# --- 조기 탈출: 이미 같은 상태면 아무것도 하지 않는다 ---
# PostToolUse 는 도구 호출마다 불리므로, 연타되는 경우 tmux show 한 번으로 끝낸다.
if [ -n "$state" ] && [ "$state" = "$(tmux show -w -t "$TMUX_PANE" -v @cc 2>/dev/null)" ]; then
  exit 0
fi

# --- 상태 이모지: 인자가 없으면 현재 @cc 값에서 유추 ---
if [ -z "$emoji" ]; then
  case "$(tmux show -w -t "$TMUX_PANE" -v @cc 2>/dev/null)" in
    busy)    emoji="⏳" ;;
    waiting) emoji="❓" ;;
    *)       emoji="✅" ;;
  esac
fi

# --- 프로필 마커 ---
# CLAUDE_ACCOUNT 는 이전 이름 — 당분간 함께 받는다
profile="${AGENT_PROFILE:-${CLAUDE_ACCOUNT:-}}"
if [ -z "$profile" ] && [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  # HUD 의 profile: 과 같은 규칙 — basename 에서 앞의 점을 뗀다.
  profile=${CLAUDE_CONFIG_DIR%/}; profile=${profile##*/}; profile=${profile#.}
fi
profile="${profile:-claude}"
marker=""
if [ -r "$CONF" ]; then
  while read -r a m _rest; do
    case "$a" in ''|\#*) continue ;; esac
    if [ "$a" = "$profile" ]; then
      [ "$m" = "-" ] || marker="$m"
      break
    fi
  done < "$CONF"
fi

# 라벨 규칙이 없으면 이름을 짓지 않는다. 훅이 실패해도 에이전트 쪽엔 영향이 없어야
# 하므로 조용히 빠진다 (./install.sh --check 가 링크 끊김을 잡아준다).
[ -r "$LABEL_LIB" ] || exit 0
. "$LABEL_LIB"

# --- 라벨 ---
label=$(tmux show -w -t "$TMUX_PANE" -v @cc_label 2>/dev/null)
if [ -n "$label" ]; then
  label=$(_agent_label_fit "$label")
else
  cwd=$(printf '%s' "$payload" \
    | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  [ -n "$cwd" ] && [ -d "$cwd" ] || cwd=$(tmux display -p -t "$TMUX_PANE" '#{pane_current_path}' 2>/dev/null)
  [ -n "$cwd" ] || cwd=$PWD
  label=$(_agent_label_of "$cwd")
fi

tmux rename-window -t "$TMUX_PANE" "$emoji$marker$label" 2>/dev/null
[ -n "$state" ] && tmux set -w -t "$TMUX_PANE" @cc "$state" 2>/dev/null
exit 0
