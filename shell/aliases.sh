# 셸 alias / 함수.  ~/.bashrc 에서 source 해서 씁니다 (shell/bashrc.snippet).
# 머신을 안 가리는 것만 둡니다. 언어·런타임 환경(conda·nvm·CUDA)은 프로젝트 소유입니다.

# 우분투 기본 .bashrc 의 `alias ll='ls -alF'` 를 덮어씁니다.
# 이 파일이 .bashrc 끝에서 source 되므로 이쪽이 이깁니다.
alias ll='ls -alFh --color=auto --group-directories-first'

# GPU 실시간 감시
alias gpuw='watch -n1 nvidia-smi'

# tmux 세션 진입.
#   t            세션이 있으면 목록에서 고르고, 없으면 현재 저장소 이름으로 만든다
#   t <이름>     그 이름으로 붙거나 만든다
# 예전엔 `tmux new -A -s dev` 로 이름이 고정돼 있었는데, 세션이 프로젝트 단위로
# 갈리지 않아 불편했다. 기본 이름은 창 이름과 같은 축(git 저장소 이름)을 쓴다.
_t_default_name() {
  local root
  if root=$(git rev-parse --show-toplevel 2>/dev/null) && [ -n "$root" ]; then
    printf '%s' "${root##*/}"
  elif [ "$PWD" = "$HOME" ]; then
    printf 'main'
  else
    printf '%s' "${PWD##*/}"
  fi
}

# 세션 이름에서 tmux 가 대상 지정에 쓰는 문자를 뺀다.
_t_sanitize() { printf '%s' "${1//[.:]/-}"; }

# 붙거나(있으면) 만들거나. tmux 안이면 attach 대신 switch-client.
_t_go() {
  local name; name=$(_t_sanitize "$1")
  if [ -n "${TMUX:-}" ]; then
    tmux has-session -t "=$name" 2>/dev/null || tmux new-session -d -s "$name" -c "$PWD" || return 1
    tmux switch-client -t "=$name"
  else
    tmux new-session -A -s "$name" -c "$PWD"
  fi
}

t() {
  if ! command -v tmux >/dev/null 2>&1; then echo "tmux 가 없습니다" >&2; return 1; fi
  [ $# -gt 0 ] && { _t_go "$*"; return; }

  local default; default=$(_t_default_name)
  local names=() rows=() line
  while IFS=$'\t' read -r n w a; do
    [ -n "$n" ] || continue
    names+=("$n"); rows+=("$(printf '%-20s %s windows%s' "$n" "$w" "$a")")
  done < <(tmux list-sessions -F $'#{session_name}\t#{session_windows}\t#{?session_attached, (attached),}' 2>/dev/null)

  if [ ${#names[@]} -eq 0 ]; then _t_go "$default"; return; fi

  local i
  for i in "${!rows[@]}"; do printf '  %d) %s\n' "$((i+1))" "${rows[$i]}"; done
  printf '  n) 새로 만들기 (%s)\n' "$default"
  local ans; read -r -p "선택> " ans

  case "$ans" in
    ''|q|Q)  return 0 ;;
    n|N)     _t_go "$default" ;;
    *[!0-9]*) echo "취소" >&2; return 1 ;;
    *)
      if [ "$ans" -ge 1 ] && [ "$ans" -le ${#names[@]} ]; then
        _t_go "${names[$((ans-1))]}"
      else
        echo "범위를 벗어났습니다" >&2; return 1
      fi ;;
  esac
}
