# 창 이름의 "라벨" 한 벌.  훅과 셸이 함께 쓴다 — source 해서 쓰는 라이브러리다.
#
#   훅  agent/window-label.sh   에이전트가 창을 점유한 동안 (이모지 + 마커 + 라벨)
#   셸  shell/agents.sh         프롬프트가 그려질 때 (라벨만)
#
# 소유권은 둘로 나뉘지만 라벨 규칙은 하나여야 한다. 예전엔 같은 3분기와 같은
# 자르기 길이가 두 파일에 각각 적혀 있었다. 한쪽만 고치면 같은 디렉토리가
# 셸일 때와 에이전트일 때 다른 이름으로 보인다 — 그걸 막으려고 여기로 합쳤다.
#
# git 브랜치는 일부러 안 쓴다 (수시로 바뀌어 식별에 도움이 안 됨).

AGENT_LABEL_MAXLEN=24

# $1 = 라벨.  너무 길면 자른다.  ccname 으로 손수 붙인 이름에도 같은 자가 간다.
_agent_label_fit() {
  local s=$1
  [ ${#s} -gt "$AGENT_LABEL_MAXLEN" ] && s="${s:0:$((AGENT_LABEL_MAXLEN-1))}…"
  printf '%s' "$s"
}

# $1 = 기준 디렉토리 (생략하면 $PWD).  결과를 stdout 으로 낸다.
_agent_label_of() {
  local cwd=${1:-$PWD} root label
  if root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) && [ -n "$root" ]; then
    label=${root##*/}
  elif [ "$cwd" = "$HOME" ]; then
    label='~'
  else
    label=${cwd##*/}
  fi
  _agent_label_fit "$label"
}
