#!/usr/bin/env bash
# 이 저장소의 설정을 ~/.claude 로 심링크한다.
#   ./install.sh          설치 / 재설치 (몇 번 돌려도 안전)
#   ./install.sh --check  링크 상태만 점검
#
# 심링크이므로 ~/.claude 에서 고쳐도 곧바로 이 저장소의 변경으로 잡힌다.
# ~/.claude 자체는 git 저장소가 아니다 (자격증명·대화기록이 들어있으므로).
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEST="$HOME/.claude"   # Claude 전용 항목의 기본 위치
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

LINKS="
agent/window-label.sh:$HOME/.local/bin/agent-window-label
agent/profiles.conf:$HOME/.config/agent-profiles.conf
shell/agents.sh:$HOME/.config/agent-dotfiles/agents.sh
claude/settings.json:$HOME/.claude/settings.json
plugins/ai-agent-dotfiles/agents:$HOME/.claude/agents
tmux/tmux.conf:$HOME/.tmux.conf
"

stamp=$(date +%Y%m%d-%H%M%S)
rc=0; ok=0; bad=0

printf '저장소: %s\n대상  : %s\n\n' "$REPO" "$DEST"

for pair in $LINKS; do
  src="$REPO/${pair%%:*}"; dst="${pair#*:}"
  [ -e "$src" ] || { printf '  없음   %s\n' "${pair%%:*}"; rc=1; continue; }

  if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
    printf '  ok     %s\n' "${pair%%:*}"; ok=$((ok+1)); continue
  fi
  bad=$((bad+1))

  if [ "$CHECK" = 1 ]; then
    [ -e "$dst" ] && printf '  분리됨 %s  (심링크 아님 → ./install.sh)\n' "${pair%%:*}" \
                  || printf '  미설치 %s\n' "${pair%%:*}"
    continue
  fi

  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    mv "$dst" "$dst.pre-install-$stamp" || { rc=1; continue; }
    printf '  백업   %s -> %s.pre-install-%s\n' "${pair%%:*}" "$(basename "$dst")" "$stamp"
  else
    rm -f "$dst"
  fi
  ln -s "$src" "$dst" && printf '  링크   %s\n' "${pair%%:*}" || rc=1
done

if [ "$CHECK" = 0 ]; then
  if grep -q 'agent-dotfiles/agents.sh' "$HOME/.bashrc" 2>/dev/null; then
    printf '  ok     .bashrc (이미 등록됨)\n'
  else
    cp "$HOME/.bashrc" "$HOME/.bashrc.pre-claude-setup-$stamp" 2>/dev/null
    { echo; cat "$REPO/shell/bashrc.snippet"; } >> "$HOME/.bashrc" \
      && printf '  추가   .bashrc 에 source 한 줄\n' || rc=1
  fi
fi

echo
if [ "$CHECK" = 1 ]; then
  [ "$bad" -eq 0 ] && echo "전부 정상 ($ok개)" || echo "복구 필요 $bad개  →  ./install.sh"
  exit 0
fi

cat <<'NEXT'
설치 완료. 남은 수동 작업:

  1. 플러그인 (omc, superpowers)
       claude 한 번 실행 → settings.json 의 enabledPlugins /
       extraKnownMarketplaces 를 보고 자동 설치됩니다.

  2. gstack  (settings.json 의 AskUserQuestion 훅이 참조, 약 1.5G)
       git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
       설치 전까지 해당 훅만 조용히 실패합니다 (나머지 기능엔 영향 없음).

  3. team 계정 (선택)
       source ~/.claude/shell/claude-accounts.sh
       claude-account-link team && claude-team    # 실행 후 /login

  4. source ~/.bashrc   또는 새 셸 열기
NEXT
exit $rc
