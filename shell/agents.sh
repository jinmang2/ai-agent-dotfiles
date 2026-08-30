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

# 공유 항목 안에서 계정별로 갈라야 하는 자식들.
#
# 규칙 하나: **설정과 내려받은 덩어리는 공유하고, 돌면서 쌓이는 상태는 계정별로 둔다.**
# 상태를 공유하면 계정끼리 서로의 값을 덮어쓴다. 실제로 겪은 사고가 아래 첫 줄이다.
#
#   plugins/oh-my-claudecode/  OMC 사용량 캐시(.usage-cache-*.json)가 사는 곳.
#     OMC 는 자격증명을 <config-dir>/.credentials.json 에서 계정별로 제대로 읽는데,
#     캐시도 <config-dir> 밑에 둔다. plugins 를 통째로 심링크하면 그 분리가 무너져
#     두 계정이 캐시 파일 하나를 나눠 쓰게 되고, 마지막으로 렌더한 계정의 5시간/주간
#     한도가 양쪽 HUD 에 다 뜬다. TTL 90초가 지나도 최대 15분까지 옛 값을 먼저
#     내주고 뒤에서 갱신하므로, 한참 동안 틀린 숫자가 굳어 있는다.
#   hooks/.omc/                OMC 훅 상태 (세션별 디렉터리 + 예전 방식의 전역 stdin 캐시)
#   hud/cache/                 스테이터스라인 렌더 캐시. 세션 id 로 갈리긴 하지만
#                              계정을 가리지 않아 두 계정 찌꺼기가 한곳에 쌓인다.
#   plugins/installed_plugins.json · known_marketplaces.json · .last_inuse_sweep
#     이건 공유하고 싶어도 못 한다. Claude Code 가 계정별로 tmp+rename 으로 다시
#     쓰고, installed_plugins.json 의 installPath 는 <config-dir> 절대경로다
#     (.claude-team 쪽은 .../.claude-team/plugins/cache/... 를 가리킨다).
#     심링크를 걸면 곧바로 실제 파일로 갈려서 claude-accounts 가 영원히 끊김을
#     보고한다. 갈라도 손해는 없다 — 실제 내용물인 cache/ 와 marketplaces/ 는
#     여전히 공유되고, 각 계정은 settings.json 을 보고 알아서 다시 채운다.
#
# 여기 없는 자식은 공유된다(기존 동작 유지). 새로 보는 자식은 relink 때
# "처음 보는" 으로 알려주므로, 상태인지 설정인지 판단해서 이 목록에 넣는다.
CLAUDE_ACCOUNT_LOCAL="plugins/oh-my-claudecode hooks/.omc hud/cache \
plugins/installed_plugins.json plugins/known_marketplaces.json plugins/.last_inuse_sweep"

# 이미 판단이 끝나 공유해도 되는 자식들. 위 알림을 조용히 시키는 용도일 뿐이다.
CLAUDE_ACCOUNT_SHARED_SEEN="plugins/cache plugins/marketplaces plugins/data \
plugins/plugin-catalog-cache.json \
hud/find-node.sh hud/lib hud/omc-hud-cache.sh hud/omc-hud.mjs"

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
  local item rc=0 stamp
  stamp=$(date +%Y%m%d-%H%M%S)

  for item in $CLAUDE_SHARED_ITEMS; do
    [ -e "$CLAUDE_SHARED_ROOT/$item" ] || continue
    if _claude_item_has_local_child "$item"; then
      _claude_link_by_child "$dir" "$item" "$stamp" || rc=1
    else
      _claude_link_one "$CLAUDE_SHARED_ROOT/$item" "$dir/$item" "$item" "$stamp" || rc=1
    fi
  done
  return $rc
}

# 링크 한 건.  $1=원본 $2=대상 $3=출력용 이름 $4=타임스탬프
_claude_link_one() {
  local src=$1 dst=$2 label=$3 stamp=$4

  if [ -L "$dst" ]; then
    if [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
      printf '  ok    %s\n' "$label"; return 0
    fi
    rm -f "$dst"
  elif [ -e "$dst" ]; then
    # 원자적 쓰기(tmp+rename)로 심링크가 실제 파일로 바뀐 경우.
    # 사용자 편집분일 수 있으므로 지우지 않고 옆으로 치운다.
    mv "$dst" "$dst.detached-$stamp" || return 1
    printf '  분리됨 %s -> %s.detached-%s 로 보존, 다시 링크합니다\n' "$label" "$(basename "$dst")" "$stamp"
  fi

  mkdir -p "$(dirname "$dst")" || return 1
  ln -s "$src" "$dst" && printf '  링크  %s\n' "$label" || return 1
}

# 이 항목 안에 계정별로 갈라야 하는 자식이 있나?
_claude_item_has_local_child() {
  local e
  for e in $CLAUDE_ACCOUNT_LOCAL; do [ "${e%%/*}" = "$1" ] && return 0; done
  return 1
}

# 항목을 통째로가 아니라 자식별로 링크한다.  CLAUDE_ACCOUNT_LOCAL 참고.
_claude_link_by_child() {
  local dir=$1 item=$2 stamp=$3
  local src="$CLAUDE_SHARED_ROOT/$item" dst="$dir/$item"
  local child rc=0

  # 예전 방식(통째 심링크)에서 넘어오는 경우. 링크만 지운다 — 원본은 그대로다.
  if [ -L "$dst" ]; then
    rm -f "$dst" && printf '  분해  %s  (통째 심링크 -> 자식별 링크)\n' "$item" || return 1
  fi
  mkdir -p "$dst" || return 1

  for child in "$src"/* "$src"/.[!.]*; do
    [ -e "$child" ] || continue
    child=${child##*/}
    case " $CLAUDE_ACCOUNT_LOCAL " in
      *" $item/$child "*)
        # 계정별 상태. 링크하지 않고 빈 디렉토리만 만들어 둔다.
        [ -d "$src/$child" ] && mkdir -p "$dst/$child"
        printf '  계정별 %s/%s\n' "$item" "$child"
        continue ;;
    esac
    case " $CLAUDE_ACCOUNT_SHARED_SEEN " in
      *" $item/$child "*) ;;
      *) printf '  처음봄 %s/%s  (상태면 CLAUDE_ACCOUNT_LOCAL, 아니면 ..._SHARED_SEEN 에 추가)\n' "$item" "$child" ;;
    esac
    _claude_link_one "$src/$child" "$dst/$child" "$item/$child" "$stamp" || rc=1
  done
  return $rc
}

# 계정 상태 점검 (링크 끊김 / 로그인 여부)
claude-accounts() {
  local acct dir login links item sub broken total
  printf '%-10s %-24s %-8s %s\n' ACCOUNT CONFIG_DIR LOGIN SHARED-LINKS
  while read -r acct; do
    dir=$(_claude_account_dir "$acct")
    [ -n "$dir" ] || continue

    login="-"; links="-"; broken=0; total=0
    [ -s "$dir/.credentials.json" ] && login="O"

    if [ "$acct" != personal ]; then
      for item in $CLAUDE_SHARED_ITEMS; do
        [ -e "$CLAUDE_SHARED_ROOT/$item" ] || continue
        if _claude_item_has_local_child "$item"; then
          # 자식별 링크여야 한다. 통째 심링크면 계정끼리 상태를 덮어쓴다.
          if [ -L "$dir/$item" ]; then
            total=$((total+1)); broken=$((broken+1))
          else
            # 링크는 점 파일 자식까지 걸므로(_claude_link_by_child) 점검도 같은 범위를 본다
            for sub in "$CLAUDE_SHARED_ROOT/$item"/* "$CLAUDE_SHARED_ROOT/$item"/.[!.]*; do
              [ -e "$sub" ] || continue
              sub=${sub##*/}
              case " $CLAUDE_ACCOUNT_LOCAL " in *" $item/$sub "*) continue ;; esac
              total=$((total+1))
              [ -L "$dir/$item/$sub" ] && [ -e "$dir/$item/$sub" ] || broken=$((broken+1))
            done
          fi
          continue
        fi
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
