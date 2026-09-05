#!/usr/bin/env bash
# tmux 창 이름을 라벨로 갱신하고, 상태·프로필은 창 옵션으로 남긴다.
# Claude Code 와 Codex 양쪽 훅에서 그대로 호출된다.
#   $1 = (호환용, 이제 안 씀) 예전엔 상태 이모지를 이름에 박았다.  배포된 훅들이
#        여전히 넘기므로 자리만 받는다.
#   $2 = 상태 문자열 (busy/waiting/done). 빈 값이면 상태는 건드리지 않음 (ccname 재렌더).
#
# 예전엔 "⏳🟠라벨" 을 통째로 이름에 넣었는데, 상태줄이 좁아지면 이모지 4칸이
# 먼저 살아남고 정작 라벨이 3자로 잘렸다.  그래서 표시를 둘로 갈랐다:
#   창 이름      = 라벨만.  choose-tree 등 어디서든 이름은 이름이다.
#   @cc          = 상태 문자열.  존재 자체가 "이 창에 에이전트가 있다" (shell/agents.sh)
#   @cc_sym      = 상태줄용 1칸 기호+색 (» busy / ? waiting / ✓ done)
#   @cc_color    = 상태줄 창 번호에 입힐 프로필 색 스타일
# 상태줄 포맷(tmux/tmux.conf)이 이 옵션들을 읽어 그린다.  옵션 이름 한 벌이
# 세 파일(여기, tmux.conf, shell/agents.sh)의 계약이다.
#
# 프로필: $AGENT_PROFILE 을 profiles.conf 에서 조회해 색을 얻는다.
#   AGENT_PROFILE 이 없으면 $CLAUDE_CONFIG_DIR 에서 유도한다 (.claude-team -> claude-team).
#   두 변수가 어긋나면 창 색과 HUD 의 profile: 이 서로 다른 계정을 가리키게 되는데,
#   실제로 그런 창이 나왔다 — CLAUDE_CONFIG_DIR 만 걸린 채 실행된 세션이 team 계정을
#   쓰면서 창에는 개인 색을 달고 있었다.  HUD 도 같은 값을 보므로 유도가 맞다.
# 라벨 우선순위: @cc_label(수동 작업명) > agent/label-of.sh 의 규칙
#   라벨 규칙 자체는 셸(shell/agents.sh)과 나눠 갖는 한 벌이다 — label-of.sh.
set -u

CONF="${AGENT_PROFILES_CONF:-$HOME/.config/agent-profiles.conf}"
LABEL_LIB="${AGENT_LABEL_LIB:-$HOME/.config/agent-dotfiles/label-of.sh}"

state="${2:-}"

[ -n "${TMUX_PANE:-}" ] || exit 0
command -v tmux >/dev/null 2>&1 || exit 0

payload=$(cat 2>/dev/null)
# 맨 앞의 "cwd" 만 본다 — 뒤에 중첩된 같은 이름의 키(tool_response 등)가 이기면 안 된다.
payload_cwd=$(printf '%s' "$payload" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' \
  | head -1 | sed 's/.*:[[:space:]]*"\([^"]*\)"$/\1/')

# --- 임시 디렉토리에서 도는 세션은 이 창의 주인이 아니다 ---
# 에이전트가 도구 안에서 `claude -p` 를 다시 띄우면(pipespec 의 CLI 어댑터가
# tempfile.TemporaryDirectory() 안에서 그렇게 한다) 그 중첩 세션도 이 훅을 부른다.
# 그대로 두면 창 이름이 `tmpy2go8nt6` 가 되고, 중첩 실행의 Stop 이 바깥 세션이 아직
# 도는데 ✓ 를 찍는다.  임시 루트 아래의 cwd 는 통째로 무시한다 — 이름도 상태도.
# 대가: 스크래치패드 워크트리(/tmp/claude-…)에서 도는 정상 세션은 라벨이 셸의 cwd
# (바깥 저장소 이름)로 남는다.  임시 디렉토리 이름이 뜨는 것보다 낫다.
# 상태 없는 호출(ccname)은 셸이 부르는 것이라 예외다 — /tmp 에서 ccname 을 쳐도 붙어야 한다.
# macOS 의 TMPDIR 은 /var/folders/…/T/ 처럼 끝에 슬래시가 붙어 오고, 없을 땐
# /private/var/folders 로 온다.
tmp_root=${TMPDIR:-/tmp}; tmp_root=${tmp_root%/}
if [ -n "$state" ]; then
  case "$payload_cwd" in
    "$tmp_root"/*|/tmp/*|/var/tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*) exit 0 ;;
  esac
fi

# --- 조기 탈출: 이미 같은 상태면 아무것도 하지 않는다 ---
# PostToolUse 는 도구 호출마다 불리므로, 연타되는 경우 tmux show 한 번으로 끝낸다.
if [ -n "$state" ] && [ "$state" = "$(tmux show -w -t "$TMUX_PANE" -v @cc 2>/dev/null)" ]; then
  exit 0
fi

# --- 상태 기호: 상태줄에서 1칸.  이모지(2칸)를 쓰지 않는 게 요점이다 ---
case "$state" in
  busy)    sym='#[fg=colour214,bold]»' ;;
  waiting) sym='#[fg=colour203,bold]?' ;;
  done)    sym='#[fg=colour114]✓' ;;
  *)       sym='' ;;
esac

# --- 프로필 색 ---
# CLAUDE_ACCOUNT 는 이전 이름 — 당분간 함께 받는다
profile="${AGENT_PROFILE:-${CLAUDE_ACCOUNT:-}}"
if [ -z "$profile" ] && [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  # HUD 의 profile: 과 같은 규칙 — basename 에서 앞의 점을 뗀다.
  profile=${CLAUDE_CONFIG_DIR%/}; profile=${profile##*/}; profile=${profile#.}
fi
profile="${profile:-claude}"
color=""
if [ -r "$CONF" ]; then
  while read -r a c _rest; do
    case "$a" in ''|\#*) continue ;; esac
    if [ "$a" = "$profile" ]; then
      [ "$c" = "-" ] || color="$c"
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
  cwd=$payload_cwd
  [ -n "$cwd" ] && [ -d "$cwd" ] || cwd=$(tmux display -p -t "$TMUX_PANE" '#{pane_current_path}' 2>/dev/null)
  [ -n "$cwd" ] || cwd=$PWD
  label=$(_agent_label_of "$cwd")
fi

tmux rename-window -t "$TMUX_PANE" "$label" 2>/dev/null
# 상태 없는 호출(ccname 재렌더)에서는 이름만 만진다.  셸에서 ccname 을 부른 경우
# 여기서 색까지 남기면 에이전트 없는 창이 프로필 색을 달고, 셸 쪽 청소는 @cc 가
# 있을 때만 돌아서 그 색이 영원히 굳는다.
if [ -n "$state" ]; then
  [ -n "$color" ] && tmux set -w -t "$TMUX_PANE" @cc_color "bg=$color,fg=colour235" 2>/dev/null
  tmux set -w -t "$TMUX_PANE" @cc "$state" 2>/dev/null
  tmux set -w -t "$TMUX_PANE" @cc_sym "$sym" 2>/dev/null
fi
exit 0
