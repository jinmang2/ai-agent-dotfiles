# Claude Code 다중 계정 지원.  ~/.bashrc 에서 source 해서 씁니다.
# 계정마다 CLAUDE_CONFIG_DIR 을 분리하되, skills/plugins/settings/hooks/hud 는
# ~/.claude 의 것을 심링크로 공유합니다.

CLAUDE_SHARED_ROOT="$HOME/.claude"

# ── 계정 등록 ─────────────────────────────────────────────────────────────
# 계정을 늘리려면 여기에 CLAUDE_ACCOUNT_DIRS_<이름> 한 줄 + profiles.conf 에 한 줄.
# 아래 함수들은 이 변수들을 자동으로 훑으므로 다른 곳은 손대지 않아도 됩니다.
CLAUDE_ACCOUNT_DIRS_team="$HOME/.claude-team"

# ~/.claude 에서 그대로 물려쓸 항목들
CLAUDE_SHARED_ITEMS="settings.json skills plugins hooks hud commands agents CLAUDE.md"

# OMC 환경변수.  ~/.claude/settings.local.json 은 Claude Code 가 읽지 않으므로
# (user 스코프 설정 파일은 settings.json 하나뿐) 셸에서 export 한다.
export ALLOW_ULTRAGOAL_WITHOUT_GOAL=1

# 등록된 계정 이름 목록 (personal 은 ~/.claude 자체라 항상 맨 앞)
_claude_account_names() {
  local v
  printf 'personal\n'
  for v in ${!CLAUDE_ACCOUNT_DIRS_@}; do printf '%s\n' "${v#CLAUDE_ACCOUNT_DIRS_}"; done
}

_claude_account_dir() {
  [ "$1" = personal ] && { printf '%s' "$CLAUDE_SHARED_ROOT"; return; }
  eval "printf '%s' \"\${CLAUDE_ACCOUNT_DIRS_$1:-}\""
}

# 계정 config 디렉토리를 만들고 공유 항목을 심링크로 (재)연결한다. 몇 번 돌려도 안전.
claude-account-link() {
  local acct="${1:?사용법: claude-account-link <계정이름>}"
  local dir; dir=$(_claude_account_dir "$acct")
  if [ -z "$dir" ] || [ "$acct" = personal ]; then
    echo "알 수 없는 계정: $acct  (등록된 계정: $(_claude_account_names | tr '\n' ' '))" >&2; return 1
  fi

  mkdir -p "$dir" || return 1
  local item src dst stamp rc=0
  stamp=$(date +%Y%m%d-%H%M%S)

  for item in $CLAUDE_SHARED_ITEMS; do
    src="$CLAUDE_SHARED_ROOT/$item"
    dst="$dir/$item"
    [ -e "$src" ] || continue

    if [ -L "$dst" ]; then
      if [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
        printf '  ok    %s\n' "$item"; continue
      fi
      rm -f "$dst"
    elif [ -e "$dst" ]; then
      # 원자적 쓰기(tmp+rename)로 심링크가 실제 파일로 바뀐 경우.
      # 사용자 편집분일 수 있으므로 지우지 않고 옆으로 치운다.
      mv "$dst" "$dst.detached-$stamp" || { rc=1; continue; }
      printf '  분리됨 %s -> %s.detached-%s 로 보존, 다시 링크합니다\n' "$item" "$item" "$stamp"
    fi

    ln -s "$src" "$dst" && printf '  링크  %s\n' "$item" || rc=1
  done
  return $rc
}

# 계정 상태 점검 (링크 끊김 / 로그인 여부)
claude-accounts() {
  local acct dir login links item broken total
  printf '%-10s %-24s %-8s %s\n' ACCOUNT CONFIG_DIR LOGIN SHARED-LINKS
  while read -r acct; do
    dir=$(_claude_account_dir "$acct")
    [ -n "$dir" ] || continue

    login="-"; links="-"; broken=0; total=0
    [ -s "$dir/.credentials.json" ] && login="O"

    if [ "$acct" != personal ]; then
      for item in $CLAUDE_SHARED_ITEMS; do
        [ -e "$CLAUDE_SHARED_ROOT/$item" ] || continue
        total=$((total+1))
        [ -L "$dir/$item" ] && [ -e "$dir/$item" ] || broken=$((broken+1))
      done
      if [ "$broken" -eq 0 ]; then links="정상 ($total)"
      else links="끊김 $broken/$total  → claude-account-link $acct"; fi
    fi
    printf '%-10s %-24s %-8s %s\n' "$acct" "${dir/#$HOME/\~}" "$login" "$links"
  done < <(_claude_account_names)
}

# 계정별 실행 함수를 자동 생성한다 (claude-team, 계정을 늘리면 claude-<이름>).
_claude_define_account_runners() {
  local acct dir
  while read -r acct; do
    [ "$acct" = personal ] && continue
    dir=$(_claude_account_dir "$acct")
    eval "claude-$acct() { CLAUDE_CONFIG_DIR='$dir' AGENT_PROFILE='claude-$acct' command claude \"\$@\"; }"
  done < <(_claude_account_names)
}
_claude_define_account_runners

# ── 창 이름: 셸이 주인일 때 ──────────────────────────────────────────────
# 에이전트가 그 창을 떠났다는 이벤트는 없다. Claude Code 의 Stop 훅은 턴 끝에
# 불릴 뿐이고, 강제 종료되면 아무 훅도 안 불린다. 그래서 종료 뒤에도 ✅🔵repo
# 가 그대로 굳는다.
#
# 대신 "셸이 프롬프트를 그렸다" 를 쓴다 — 그건 그 창에 전경 프로그램이 없을
# 때만 일어나므로 정확히 "에이전트가 없다" 와 같다. 에이전트 실행 중에는
# 프롬프트가 안 그려지니 훅과 싸우지 않는다.
#
#   셸이 주인   ->  이모지 없이 이름만      (여기)
#   에이전트    ->  ⏳🔵 붙은 이름          (agent/window-label.sh)
#
# 그래서 이모지가 붙어 있으면 그 창에 에이전트가 살아있다는 뜻이 된다.
declare -A _CC_LABEL_CACHE=()

_cc_shell_window_name() {
  [ -n "${TMUX_PANE:-}" ] || return 0

  local out cur manual want root
  out=$(tmux display -p -t "$TMUX_PANE" "#{window_name}"$'\t'"#{@cc_label}" 2>/dev/null) || return 0
  IFS=$'\t' read -r cur manual <<< "$out"

  if [ -n "$manual" ]; then
    want=$manual                      # ccname 으로 고정한 작업명이 최우선
  else
    want=${_CC_LABEL_CACHE[$PWD]-}    # git 호출은 디렉토리당 한 번만
    if [ -z "$want" ]; then
      if root=$(git rev-parse --show-toplevel 2>/dev/null) && [ -n "$root" ]; then
        want=${root##*/}
      elif [ "$PWD" = "$HOME" ]; then
        want='~'
      else
        want=${PWD##*/}
      fi
      [ ${#want} -gt 24 ] && want="${want:0:23}…"
      _CC_LABEL_CACHE[$PWD]=$want
    fi
  fi

  [ "$cur" = "$want" ] && return 0    # 이미 맞으면 tmux 호출 없이 끝
  tmux rename-window -t "$TMUX_PANE" "$want" 2>/dev/null
  tmux set -uw -t "$TMUX_PANE" @cc 2>/dev/null   # 다음 에이전트가 깨끗하게 시작하도록
}

# 중복 등록 방지 (agents.sh 를 다시 source 해도 안전)
case "${PROMPT_COMMAND:-}" in
  *_cc_shell_window_name*) ;;
  *) PROMPT_COMMAND="_cc_shell_window_name${PROMPT_COMMAND:+; $PROMPT_COMMAND}" ;;
esac

# 현재 tmux 창의 작업명을 고정/해제.  Claude Code 안에서는 `!ccname 작업명` 으로.
ccname() {
  if [ -z "${TMUX_PANE:-}" ]; then echo "tmux 안에서만 동작합니다" >&2; return 1; fi
  if [ $# -eq 0 ] || [ "$1" = --clear ] || [ "$1" = -c ]; then
    tmux set -uw -t "$TMUX_PANE" @cc_label 2>/dev/null
  else
    tmux set -w -t "$TMUX_PANE" @cc_label "$*" 2>/dev/null
  fi
  printf '{"cwd":"%s"}' "$PWD" | agent-window-label "" ""
  tmux display -p -t "$TMUX_PANE" '#{window_name}'
}
