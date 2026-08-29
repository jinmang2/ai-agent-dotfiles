#!/usr/bin/env bash
# 이 저장소의 설정을 각 도구의 설정 위치로 심링크한다.
#   ./install.sh          설치 / 재설치 (몇 번 돌려도 안전)
#   ./install.sh --check  링크 상태만 점검
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
[ "${1:-}" = "--check" ] && CHECK=1

# 저장소경로:설치위치.  한 줄에 하나. 경로에 공백이 있어도 안전하도록 while read 로 읽는다.
# ~/.claude/agents 는 일부러 없다 — 서브에이전트는 플러그인으로 배포된다 (docs/plugins.md).
LINKS=$(cat <<'LIST'
agent/window-label.sh|$HOME/.local/bin/agent-window-label
agent/profiles.conf|$HOME/.config/agent-profiles.conf
shell/agents.sh|$HOME/.config/agent-dotfiles/agents.sh
tmux/tmux.conf|$HOME/.tmux.conf
gemini/GEMINI.md|$HOME/.gemini/GEMINI.md
LIST
)

stamp=$(date +%Y%m%d-%H%M%S)
rc=0; ok=0; bad=0

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
      printf '  갱신필요 claude/settings.json  (병합 결과와 다름 → ./install.sh)\n'; bad=$((bad+1))
    fi
  else
    mkdir -p "$(dirname "$DST_SETTINGS")"
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

# ── .bashrc ─────────────────────────────────────────────────────────────
# 예전 방식으로 손수 넣은 `alias claude-team=...` 이 남아 있으면 agents.sh 의
# claude-team 함수를 가린다 (alias 확장이 함수 조회보다 먼저 일어난다).
if grep -qE '^\s*alias\s+claude-[a-z]+=' "$HOME/.bashrc" 2>/dev/null; then
  if [ "$CHECK" = 1 ]; then
    printf '  충돌   .bashrc 의 alias claude-* 가 agents.sh 함수를 가림 → ./install.sh\n'
    bad=$((bad+1))
  else
    cp "$HOME/.bashrc" "$HOME/.bashrc.pre-install-$stamp" 2>/dev/null
    sed -i -E 's/^(\s*alias\s+claude-[a-z]+=.*)$/# [ai-agent-dotfiles] agents.sh 의 함수로 대체됨: \1/' "$HOME/.bashrc" \
      && printf '  주석   .bashrc 의 alias claude-* (agents.sh 함수로 대체)\n' || rc=1
  fi
fi

if [ "$CHECK" = 0 ]; then
  if grep -q 'agent-dotfiles/agents.sh' "$HOME/.bashrc" 2>/dev/null; then
    printf '  ok     .bashrc (이미 등록됨)\n'
  else
    cp "$HOME/.bashrc" "$HOME/.bashrc.pre-install-$stamp" 2>/dev/null
    { echo; cat "$REPO/shell/bashrc.snippet"; } >> "$HOME/.bashrc" \
      && printf '  추가   .bashrc 에 source 한 줄\n' || rc=1
  fi
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
  [ "$bad" -eq 0 ] && echo "전부 정상 ($ok개)" || echo "복구 필요 $bad개  →  ./install.sh"
  exit 0
fi

cat <<'NEXT'

설치 완료. 남은 수동 작업:

  1. 플러그인
       claude 한 번 실행 → settings.json 의 enabledPlugins /
       extraKnownMarketplaces 를 보고 자동 설치됩니다.
       서브에이전트(inspector)도 ai-agent-dotfiles 플러그인으로 함께 들어옵니다.

  2. gstack  (settings.json 의 AskUserQuestion 훅이 참조, 약 1.5G)
       git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
       설치 전까지 해당 훅만 조용히 실패합니다 (나머지 기능엔 영향 없음).

  3. team 계정 (선택)
       claude-account-link team && claude-team    # 실행 후 /login

  4. source ~/.bashrc   또는 새 셸 열기
NEXT
exit $rc
