# Claude Code 다중 계정 지원.  ~/.bashrc 에서 source 해서 씁니다.
# 계정마다 CLAUDE_CONFIG_DIR 을 분리하되, skills/plugins/settings/hooks/hud 는
# ~/.claude 의 것을 심링크로 공유합니다.

CLAUDE_SHARED_ROOT="$HOME/.claude"
# 계정 이름 -> config 디렉토리.  계정을 늘리려면 여기와 profiles.conf 에 한 줄씩.
CLAUDE_ACCOUNT_DIRS_team="$HOME/.claude-team"

# ~/.claude 에서 그대로 물려쓸 항목들
CLAUDE_SHARED_ITEMS="settings.json skills plugins hooks hud commands agents CLAUDE.md"

# 계정 config 디렉토리를 만들고 공유 항목을 심링크로 (재)연결한다. 몇 번 돌려도 안전.
claude-account-link() {
  local acct="${1:?사용법: claude-account-link <계정이름>}"
  local dir; dir=$(eval "printf '%s' \"\${CLAUDE_ACCOUNT_DIRS_$acct:-}\"")
  if [ -z "$dir" ]; then
    echo "알 수 없는 계정: $acct" >&2; return 1
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
  local acct dir
  printf '%-10s %-24s %-10s %s\n' 계정 CONFIG_DIR 로그인 공유링크
  for acct in personal team; do
    if [ "$acct" = personal ]; then dir="$CLAUDE_SHARED_ROOT"
    else dir=$(eval "printf '%s' \"\${CLAUDE_ACCOUNT_DIRS_$acct:-}\""); fi
    [ -n "$dir" ] || continue

    local login=없음 links=- item broken=0 total=0
    [ -s "$dir/.credentials.json" ] && login=있음

    if [ "$acct" != personal ]; then
      for item in $CLAUDE_SHARED_ITEMS; do
        [ -e "$CLAUDE_SHARED_ROOT/$item" ] || continue
        total=$((total+1))
        [ -L "$dir/$item" ] && [ -e "$dir/$item" ] || broken=$((broken+1))
      done
      if [ "$broken" -eq 0 ]; then links="정상 ($total)"; else links="끊김 $broken/$total  → claude-account-link $acct"; fi
    fi
    printf '%-10s %-24s %-10s %s\n' "$acct" "${dir/#$HOME/\~}" "$login" "$links"
  done
}

# team 계정으로 실행
claude-team() {
  CLAUDE_CONFIG_DIR="$CLAUDE_ACCOUNT_DIRS_team" AGENT_PROFILE=claude-team command claude "$@"
}

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
