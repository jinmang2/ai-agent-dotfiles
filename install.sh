#!/usr/bin/env bash
# 이 저장소의 설정을 각 도구의 설정 위치로 심링크한다.
#   ./install.sh             설치 / 재설치 (몇 번 돌려도 안전)
#   ./install.sh --check     링크 상태만 점검
#   ./install.sh --ssh-diff  ~/.ssh/config 이 다를 때 그 차이까지 출력
#                            (--check 와 같이 쓴다. tailnet 호스트명이 화면에 나온다)
#
# 심링크이므로 ~/.claude 에서 고쳐도 곧바로 이 저장소의 변경으로 잡힌다.
# ~/.claude 자체는 git 저장소가 아니다 (자격증명·대화기록이 들어있으므로).
#
# 예외 하나: local/hosts/<호스트>/settings-overlay.json 이 있으면 settings.json 은
# 심링크가 아니라 "공통 + 오버레이" 를 합친 실제 파일로 생성된다. 자세한 건 --check 출력.
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# 머신 이름. local/hosts/<이름>/ 을 찾는 키다.
# WSL 처럼 hostname 이 바뀔 수 있는 환경에서는 AGENT_DOTFILES_HOST 로 고정한다.
HOST="${AGENT_DOTFILES_HOST:-$(hostname | tr '[:upper:]' '[:lower:]')}"
HOSTDIR="$REPO/local/hosts/$HOST"
OVERLAY="$HOSTDIR/settings-overlay.json"
CHECK=0
SSH_DIFF=0
for arg in "$@"; do
  case "$arg" in
    --check)    CHECK=1 ;;
    --ssh-diff) SSH_DIFF=1 ;;
    -h|--help)  sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) printf '알 수 없는 옵션: %s  (--check | --ssh-diff)\n' "$arg" >&2; exit 2 ;;
  esac
done

# 저장소경로:설치위치.  한 줄에 하나. 경로에 공백이 있어도 안전하도록 while read 로 읽는다.
# ~/.claude/agents 는 일부러 없다 — 서브에이전트는 플러그인으로 배포된다 (docs/plugins.md).
LINKS=$(cat <<'LIST'
agent/window-label.sh|$HOME/.local/bin/agent-window-label
agent/profiles.conf|$HOME/.config/agent-profiles.conf
shell/agents.sh|$HOME/.config/agent-dotfiles/agents.sh
shell/aliases.sh|$HOME/.config/agent-dotfiles/aliases.sh
tmux/tmux.conf|$HOME/.tmux.conf
gemini/GEMINI.md|$HOME/.gemini/GEMINI.md
LIST
)

stamp=$(date +%Y%m%d-%H%M%S)
# bad = 이 스크립트가 고칠 수 있는 것.  warn = 사람이 판단할 것(자동으로 안 건드린다).
rc=0; ok=0; bad=0; warn=0

printf '저장소: %s\n호스트: %s\n\n' "$REPO" "$HOST"

backup_or_clear() {  # $1 = 대상 경로.  실제 파일이면 옆으로 치우고, 심링크면 지운다.
  local dst=$1
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    mv "$dst" "$dst.pre-install-$stamp" || return 1
    printf '  백업   %s -> %s.pre-install-%s\n' "${dst/#$HOME/\~}" "$(basename "$dst")" "$stamp"
  else
    rm -f "$dst"
  fi
}

while IFS='|' read -r rel dsttmpl; do
  [ -n "$rel" ] || continue
  src="$REPO/$rel"
  dst=$(eval "printf '%s' \"$dsttmpl\"")

  [ -e "$src" ] || { printf '  없음   %s\n' "$rel"; rc=1; continue; }

  if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
    printf '  ok     %s\n' "$rel"; ok=$((ok+1)); continue
  fi
  bad=$((bad+1))

  if [ "$CHECK" = 1 ]; then
    [ -e "$dst" ] && printf '  분리됨 %s  (심링크 아님 → ./install.sh)\n' "$rel" \
                  || printf '  미설치 %s\n' "$rel"
    continue
  fi

  mkdir -p "$(dirname "$dst")"
  backup_or_clear "$dst" || { rc=1; continue; }
  ln -s "$src" "$dst" && printf '  링크   %s\n' "$rel" || rc=1
done <<< "$LINKS"

# ── settings.json: 오버레이가 있으면 병합 생성, 없으면 심링크 ──────────────
SRC_SETTINGS="$REPO/claude/settings.json"
DST_SETTINGS="$HOME/.claude/settings.json"

if [ -f "$OVERLAY" ]; then
  if [ "$CHECK" = 1 ]; then
    if [ -L "$DST_SETTINGS" ]; then
      printf '  분리됨 claude/settings.json  (오버레이가 있는데 심링크 상태 → ./install.sh)\n'; bad=$((bad+1))
    elif [ -f "$DST_SETTINGS" ] && "$REPO/scripts/merge-settings.py" --check "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS"; then
      printf '  ok     claude/settings.json  (병합 생성 + %s)\n' "local/hosts/$HOST/settings-overlay.json"; ok=$((ok+1))
    else
      printf '  갱신필요 claude/settings.json  (병합 결과와 다름 → ./install.sh)\n'
      "$REPO/scripts/merge-settings.py" --diff "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS"
      bad=$((bad+1))
    fi
  elif [ -f "$DST_SETTINGS" ] && [ ! -L "$DST_SETTINGS" ] \
       && "$REPO/scripts/merge-settings.py" --check "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS"; then
    # 이미 병합 결과와 같다. 다시 쓰면 백업 파일만 쌓이므로 건드리지 않는다.
    printf '  ok     claude/settings.json  (병합 생성 + local/hosts/%s/settings-overlay.json)\n' "$HOST"
    ok=$((ok+1))
  else
    mkdir -p "$(dirname "$DST_SETTINGS")"
    # 덮어쓰기 전에 무엇이 달라지는지 보여준다. 백업은 남지만, 손으로 고친 게
    # 사라지는 걸 나중에 알아채는 것보다 지금 보이는 게 낫다.
    if [ -f "$DST_SETTINGS" ] && ! "$REPO/scripts/merge-settings.py" --check "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS"; then
      printf '  claude/settings.json 이 이렇게 바뀝니다:\n'
      "$REPO/scripts/merge-settings.py" --diff "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS"
    fi
    if "$REPO/scripts/merge-settings.py" "$SRC_SETTINGS" "$OVERLAY" "$DST_SETTINGS.tmp-$stamp"; then
      backup_or_clear "$DST_SETTINGS"
      mv "$DST_SETTINGS.tmp-$stamp" "$DST_SETTINGS" \
        && printf '  병합   claude/settings.json + local/hosts/%s/settings-overlay.json\n' "$HOST" || rc=1
    else
      rm -f "$DST_SETTINGS.tmp-$stamp"; printf '  실패   settings.json 병합\n'; rc=1
    fi
  fi
else
  if [ -L "$DST_SETTINGS" ] && [ "$(readlink -f "$DST_SETTINGS")" = "$(readlink -f "$SRC_SETTINGS")" ]; then
    printf '  ok     claude/settings.json\n'; ok=$((ok+1))
  elif [ "$CHECK" = 1 ]; then
    bad=$((bad+1))
    [ -e "$DST_SETTINGS" ] && printf '  분리됨 claude/settings.json  (심링크 아님 → ./install.sh)\n' \
                           || printf '  미설치 claude/settings.json\n'
  else
    bad=$((bad+1))
    mkdir -p "$(dirname "$DST_SETTINGS")"
    backup_or_clear "$DST_SETTINGS" && ln -s "$SRC_SETTINGS" "$DST_SETTINGS" \
      && printf '  링크   claude/settings.json\n' || rc=1
  fi
fi

# ── ~/.claude/hud (statusLine) ───────────────────────────────────────────
# settings.json 의 statusLine 이 ~/.claude/hud/ 의 스크립트를 부른다. 그 스크립트는
# OMC 가 만들어 놓는 것이라 이 저장소에는 없다. 없으면 statusLine 명령이 stdout 에
# 아무것도 못 내고, Claude 는 경고 없이 그냥 빈 줄을 그린다 — 알아채기 어렵다.
#
# 그래서 OMC 마켓플레이스 클론에서 직접 가져온다. `omc setup` 이 하는 일의 HUD
# 부분만 떼어낸 것이다. omc setup 을 안 쓰는 이유는 --check 가 감시하지 못하고
# 복원 절차가 하나 늘기 때문이지, omc setup 이 위험해서가 아니다 (README 참고).
# 심링크가 아니라 복사인 이유: 플러그인 디렉터리는 업데이트 때 통째로 갈린다.
#
# 프로필을 나눠 써도 ~/.claude-team/hud 등은 여기로 심링크된다 (shell/agents.sh).
HUD_SRC="$HOME/.claude/plugins/marketplaces/omc/scripts"
HUD_DST="$HOME/.claude/hud"
# 원본|설치이름|권한
HUD_FILES=$(cat <<'LIST'
find-node.sh|find-node.sh|755
lib/config-dir.mjs|lib/config-dir.mjs|644
lib/config-dir.sh|lib/config-dir.sh|644
lib/hud-cache-wrapper.sh|omc-hud-cache.sh|755
lib/hud-wrapper-template.txt|omc-hud.mjs|755
LIST
)

if [ ! -d "$HUD_SRC" ]; then
  printf '  건너뜀 ~/.claude/hud  (OMC 마켓플레이스가 아직 없음 — claude 실행 후 다시)\n'
else
  hud_total=0; hud_stale=0; hud_missing_src=0
  while IFS='|' read -r hrel hname hmode; do
    [ -n "$hrel" ] || continue
    hud_total=$((hud_total+1))
    [ -f "$HUD_SRC/$hrel" ] || { hud_missing_src=$((hud_missing_src+1)); continue; }
    cmp -s "$HUD_SRC/$hrel" "$HUD_DST/$hname" || hud_stale=$((hud_stale+1))
  done <<< "$HUD_FILES"

  if [ "$hud_missing_src" -gt 0 ]; then
    printf '  건너뜀 ~/.claude/hud  (OMC 쪽 원본 %d개 없음 — 버전이 바뀐 듯)\n' "$hud_missing_src"
  elif [ "$hud_stale" -eq 0 ]; then
    printf '  ok     ~/.claude/hud  (%d개)\n' "$hud_total"; ok=$((ok+1))
  elif [ "$CHECK" = 1 ]; then
    bad=$((bad+1))
    printf '  갱신필요 ~/.claude/hud  (%d/%d개가 OMC 원본과 다름 → ./install.sh)\n' "$hud_stale" "$hud_total"
  else
    bad=$((bad+1))
    mkdir -p "$HUD_DST/lib"
    while IFS='|' read -r hrel hname hmode; do
      [ -n "$hrel" ] || continue
      cmp -s "$HUD_SRC/$hrel" "$HUD_DST/$hname" && continue
      cp "$HUD_SRC/$hrel" "$HUD_DST/$hname" && chmod "$hmode" "$HUD_DST/$hname" || rc=1
    done <<< "$HUD_FILES"
    printf '  복사   ~/.claude/hud  (%d개 ← OMC 플러그인)\n' "$hud_stale"
  fi
fi

# ── ~/.ssh/config ────────────────────────────────────────────────────────
# 심링크하지 않는다. 600 권한이 필요하고, 도구들이 이 파일을 직접 고치기도 한다.
# 없으면 비공개 서브모듈의 것을 복사하고, 이미 있으면 손대지 않고 차이만 보여준다.
SRC_SSH="$REPO/local/ssh-config"
DST_SSH="$HOME/.ssh/config"
if [ -f "$SRC_SSH" ]; then
  if [ ! -e "$DST_SSH" ]; then
    if [ "$CHECK" = 1 ]; then
      printf '  미설치 ~/.ssh/config  (→ ./install.sh 가 local/ssh-config 를 복사)\n'; bad=$((bad+1))
    else
      mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
      cp "$SRC_SSH" "$DST_SSH" && chmod 600 "$DST_SSH" \
        && printf '  복사   local/ssh-config -> ~/.ssh/config (600)\n' || rc=1
    fi
  elif diff -q "$SRC_SSH" "$DST_SSH" >/dev/null 2>&1; then
    printf '  ok     ~/.ssh/config\n'; ok=$((ok+1))
  else
    # 손대지 않는다. ssh 설정은 잘못 덮어쓰면 접속 자체가 막힌다.
    # ok 도 bad 도 아니다 — 사람이 판단할 것이므로 warn 으로 세고 요약에 남긴다.
    warn=$((warn+1))
    n=$(diff -u "$DST_SSH" "$SRC_SSH" 2>/dev/null | sed -n '3,$p' | grep -c '^[+-]')
    printf '  다름   ~/.ssh/config  (%s줄 — 직접 판단하세요, 자동으로 덮어쓰지 않습니다)\n' "$n"
    if [ "$SSH_DIFF" = 1 ]; then
      diff -u "$DST_SSH" "$SRC_SSH" 2>/dev/null | sed -n '3,$p' | sed 's/^/    /' | head -30
    else
      # 기본값으로는 찍지 않는다. tailnet 호스트명·사용자명이 든 비공개 서브모듈 내용이라,
      # 에이전트가 --check 를 돌리기만 해도 대화 기록에 그대로 남는다.
      printf '         차이 보기: ./install.sh --ssh-diff\n'
    fi
  fi
fi

# ── .bashrc ─────────────────────────────────────────────────────────────
# 예전 방식으로 손수 넣은 `alias claude-team=...` 이 남아 있으면 agents.sh 의
# claude-team 함수를 가린다 (alias 확장이 함수 조회보다 먼저 일어난다).
#
# 계정 이름은 shell/agents.sh 의 CLAUDE_ACCOUNT_DIRS_<이름> 한 곳에서만 늘어난다
# (docs/machines.md). 그 목록으로 패턴을 만들어 **등록된 계정 이름만** 건드린다.
# 예전엔 claude-[a-z]+ 를 통째로 잡아서, 손수 만든 claude-yolo 같은 무관한 alias 까지
# 주석 처리하면서 정작 claude-team2 · claude_work 는 놓쳤다.
ACCOUNTS=""
while read -r a; do
  [ -n "$a" ] && ACCOUNTS="${ACCOUNTS:+$ACCOUNTS|}$a"
done < <(sed -n 's/^CLAUDE_ACCOUNT_DIRS_\([A-Za-z0-9_]\{1,\}\)=.*/\1/p' "$REPO/shell/agents.sh")

if [ -n "$ACCOUNTS" ] \
   && grep -qE "^[[:space:]]*alias[[:space:]]+claude-($ACCOUNTS)=" "$HOME/.bashrc" 2>/dev/null; then
  if [ "$CHECK" = 1 ]; then
    printf '  충돌   .bashrc 의 alias claude-{%s} 가 agents.sh 함수를 가림 → ./install.sh\n' "$ACCOUNTS"
    bad=$((bad+1))
  else
    cp "$HOME/.bashrc" "$HOME/.bashrc.pre-install-$stamp" 2>/dev/null
    sed -i -E "s/^([[:space:]]*alias[[:space:]]+claude-($ACCOUNTS)=.*)$/# [ai-agent-dotfiles] agents.sh 의 함수로 대체됨: \1/" "$HOME/.bashrc" \
      && printf '  주석   .bashrc 의 alias claude-{%s} (agents.sh 함수로 대체)\n' "$ACCOUNTS" || rc=1
  fi
fi

# 스니펫은 센티넬로 감싼 블록 하나다. 있으면 통째로 갈아끼우고, 없으면 덧붙인다.
# 그래야 항목이 늘어도 .bashrc 에 줄이 쌓이지 않는다.
bashrc_block_current() {
  [ -f "$HOME/.bashrc" ] || return 1
  sed -n '/^# >>> ai-agent-dotfiles >>>$/,/^# <<< ai-agent-dotfiles <<<$/p' "$HOME/.bashrc"
}

if [ "$(bashrc_block_current)" = "$(cat "$REPO/shell/bashrc.snippet")" ]; then
  printf '  ok     .bashrc\n'; [ "$CHECK" = 1 ] && ok=$((ok+1))
elif [ "$CHECK" = 1 ]; then
  bad=$((bad+1))
  bashrc_block_current | grep -q . && printf '  갱신필요 .bashrc 블록  (→ ./install.sh)\n' \
                                   || printf '  미설치 .bashrc 블록\n'
else
  cp "$HOME/.bashrc" "$HOME/.bashrc.pre-install-$stamp" 2>/dev/null
  if bashrc_block_current | grep -q .; then
    sed -i '/^# >>> ai-agent-dotfiles >>>$/,/^# <<< ai-agent-dotfiles <<</d' "$HOME/.bashrc"
    printf '  갱신   .bashrc 블록\n'
  else
    # 센티넬 없이 예전 방식으로 넣은 source 한 줄이 있으면 지운다 (중복 방지)
    sed -i '/agent-dotfiles\/agents\.sh/d; /^# Claude Code 다중 계정/d' "$HOME/.bashrc"
    printf '  추가   .bashrc 블록\n'
  fi
  { echo; cat "$REPO/shell/bashrc.snippet"; } >> "$HOME/.bashrc" || rc=1
fi

# ── local/ 서브모듈 안내 ──────────────────────────────────────────────────
echo
if [ ! -f "$REPO/local/README.md" ]; then
  echo "참고: local/ 서브모듈이 비어 있습니다 (비공개 저장소)."
  echo "      git submodule update --init   후 다시 실행하면 ssh-config 와"
  echo "      호스트별 settings 오버레이를 가져옵니다. 없어도 나머지는 정상 동작합니다."
elif [ ! -d "$HOSTDIR" ]; then
  echo "참고: 이 호스트($HOST)의 local/hosts/$HOST/ 가 없습니다."
  echo "      머신 고유 설정이 필요해지면 그때 만들면 됩니다 (docs/checklist.md)."
fi

if [ "$CHECK" = 1 ]; then
  if [ "$bad" -eq 0 ]; then printf '전부 정상 (%d개)' "$ok"
  else                      printf '복구 필요 %d개  →  ./install.sh' "$bad"; fi
  [ "$warn" -gt 0 ] && printf '  ·  확인 필요 %d개' "$warn"
  echo
  exit 0
fi

cat <<'NEXT'

설치 완료. 남은 수동 작업:

  1. 플러그인
       claude 한 번 실행 → settings.json 의 enabledPlugins /
       extraKnownMarketplaces 를 보고 자동 설치됩니다.
       서브에이전트(inspector)도 ai-agent-dotfiles 플러그인으로 함께 들어옵니다.
       깔린 뒤 ./install.sh 를 한 번 더 → ~/.claude/hud (스테이터스라인) 이
       OMC 플러그인에서 채워집니다.

  2. gstack  (settings.json 의 AskUserQuestion 훅이 참조, 약 1.5G)
       git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
       설치 전까지 해당 훅만 조용히 실패합니다 (나머지 기능엔 영향 없음).

  3. team 계정 (선택)
       claude-account-link team && claude-team    # 실행 후 /login

  4. source ~/.bashrc   또는 새 셸 열기
NEXT
exit $rc
