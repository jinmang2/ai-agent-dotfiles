# 훅 레퍼런스 — Claude Code · Codex

이 저장소의 `claude/settings.json` 과 `codex/hooks.snippet.json` 을 읽고 고치는 데 필요한 것.
2026-08-30 기준 · Claude Code 2.1.251 · codex-cli 0.151.0.

## 두 도구의 훅 형식은 같다

```json
{"hooks": {"<이벤트>": [{"matcher": "<정규식>", "hooks": [
  {"type": "command", "command": "...", "timeout": 5, "async": true}
]}]}}
```

Claude Code 는 `~/.claude/settings.json` 안에, Codex 는 `~/.codex/hooks.json` 에 둔다.
그래서 `agent/window-label.sh` 하나를 양쪽에서 그대로 쓴다.

**user 스코프 설정 파일은 `~/.claude/settings.json` 하나뿐이다.** Claude Code 가 읽는
설정 파일은 managed / `--settings` / `.claude/settings.local.json` (프로젝트) /
`.claude/settings.json` (프로젝트) / `~/.claude/settings.json` (user) 다섯이고,
`~/.claude/settings.local.json` 은 **목록에 없다 — 만들어도 조용히 무시된다.**
그래서 머신 고유 설정은 파일을 나누는 대신 설치 시점에 합친다 (`docs/machines.md`).
OMC 같은 도구의 환경변수는 셸에서 export 한다 (`shell/agents.sh`).

## 이벤트 대응표

| 하는 일 | Claude Code | Codex |
|---|---|---|
| 프롬프트 제출 시 | `UserPromptSubmit` | `UserPromptSubmit` |
| 승인 요청 뜰 때 | `Notification` | `PermissionRequest` |
| 도구 실행 전 | `PreToolUse` | `PreToolUse` |
| 도구 실행 후 | `PostToolUse` | `PostToolUse` |
| 도구 실패 후 | `PostToolUseFailure` | — |
| 턴 종료 | `Stop` | `Stop` |
| 세션 시작/종료 | `SessionStart` / `SessionEnd` | `SessionStart` / `SessionEnd` |
| 서브에이전트 | `SubagentStart` / `SubagentStop` | `SubagentStart` / `SubagentStop` |
| 컴팩션 | `PreCompact` / `PostCompact` | `PreCompact` / `PostCompact` |

Claude Code 는 이 외에도 `PermissionRequest` `PermissionDenied` `TaskCreated`
`TaskCompleted` `FileChanged` `CwdChanged` `MessageDisplay` 등을 더 갖는다.

## stdin 으로 오는 것

두 도구 모두 JSON 한 덩어리를 stdin 으로 준다. 공통 필드:

```json
{"session_id":"...", "transcript_path":"...", "cwd":"...",
 "hook_event_name":"PostToolUse", "model":"...", "permission_mode":"..."}
```

도구 이벤트면 `tool_name` · `tool_input` 이 붙고, `PostToolUse` 면 `tool_response` 도 붙는다.

**`cwd` 가 중요하다.** tmux 의 `#{pane_current_path}` 는 *셸* 의 cwd 라서 세션이
`/cwd` 로 옮겨가도 안 따라간다. 훅 JSON 의 `cwd` 가 세션의 실제 작업 디렉토리다.

`jq` 가 없는 머신을 대비해 `window-label.sh` 는 `sed` 로 뽑는다:

```bash
cwd=$(printf '%s' "$payload" \
  | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
```

## stdout 으로 돌려줄 수 있는 것

```json
{"continue": false, "stopReason": "...", "systemMessage": "사용자에게 보일 경고",
 "suppressOutput": true,
 "hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "allow|deny|ask",
                        "permissionDecisionReason": "..."}}
```

- `permissionDecision` 은 `PreToolUse` 전용. 문서엔 `allow|deny|ask` 만 있지만
  **`defer` 도 실제로 처리된다** (gstack 훅이 이걸 쓴다).
- 아무것도 안 돌려주면 그냥 통과한다. 창 이름 훅처럼 부수효과만 내는 훅은 출력이 필요 없다.

## 동기 · 비동기

| 옵션 | 언제 |
|---|---|
| (기본, 동기) | 반환값으로 진행을 통제할 때. `permissionDecision` 을 쓰는 훅 |
| `"async": true` | 부수효과만 낼 때. 창 이름·알림·로깅 |
| `"asyncRewake": true` | 백그라운드로 돌다가 exit 2 면 모델을 깨움 |

`timeout` 은 초 단위, 기본 60초다. 장식용 훅에 타임아웃이 없으면 무언가 멈췄을 때
턴 전체가 멈춘다.

## 연타되는 이벤트를 다루는 법

`PostToolUse` 는 **도구 호출마다** 불린다. 매번 전체 작업을 하면 낭비다.
`window-label.sh` 는 상태가 이미 같으면 즉시 빠져나온다:

```bash
if [ -n "$state" ] && [ "$state" = "$(tmux show -w -t "$TMUX_PANE" -v @cc 2>/dev/null)" ]; then
  exit 0
fi
```

실측: 조기 탈출 10ms, 전체 렌더 21ms (2026-08-29, WSL2).

조기 탈출의 판단 기준은 **상태값 하나**다. 그래서 상태가 그대로인 채 cwd 만 바뀌면
창 이름이 잠시 옛 저장소 이름으로 남는다. 상태는 매 턴 `busy → done` 을 오가므로
다음 턴에 저절로 맞춰진다. `ccname` 은 상태를 빈 값으로 넘겨 이 탈출을 건너뛴다.

## 훅으로 알 수 없는 것 — 에이전트가 창을 떠났다

`Stop` 은 **턴** 이 끝날 때 불린다. 세션이 끝날 때가 아니다. `SessionEnd` 가 있긴
하지만 강제 종료(`kill`, 터미널 닫기)에는 아무 훅도 안 불린다. 그래서 훅만으로는
"이 창에 이제 에이전트가 없다" 를 알 수 없고, 상태줄에 완료 기호가 굳는다.

대신 셸을 쓴다. **프롬프트가 그려졌다 = 이 창에 전경 프로그램이 없다** 이고,
이건 정확히 "에이전트가 없다" 와 같다.

| 주인 | 언제 | 무엇을 쓰나 |
|---|---|---|
| 에이전트 | 창을 점유한 동안 | 훅 → `agent/window-label.sh` (이름 + 상태·색 옵션) |
| 셸 | 프롬프트가 그려질 때 | `PROMPT_COMMAND` → `_cc_shell_window_name` (이름 + 옵션 청소) |

나뉘는 건 **소유권이지 규칙이 아니다.** 라벨을 짓는 규칙(git 저장소 이름 → `~` →
디렉토리 이름, 24자에서 자르기)은 `agent/label-of.sh` 한 벌이고 양쪽이 그걸 source
한다. 예전엔 두 파일에 각각 적혀 있어서, 한쪽만 고치면 같은 디렉토리가 셸일 때와
에이전트일 때 다른 이름으로 보였다 — 실제로 `ccname` 으로 붙인 긴 작업명이 훅에서만
잘리고 셸에서는 안 잘리고 있었다.

에이전트가 도는 동안엔 프롬프트가 안 그려지므로 둘이 안 싸운다. 종료되면 셸이
프롬프트를 그리면서 상태 옵션(`@cc` `@cc_sym` `@cc_color`)을 지운다. 덤으로
**상태줄 기호 유무 = 에이전트 생존 여부** 라는 의미가 생긴다. 상태·프로필이
창 이름이 아니라 옵션에 사는 이유는 상태줄 폭이다 — 이모지 4칸을 이름에 박으면
좁은 상태줄에서 라벨이 3자만 남는다 (tmux/tmux.conf 의 포맷 주석 참고).
이름이 양쪽 다 라벨뿐이라, 셸은 이름 비교만으로 빠지지 말고 `@cc` 가 남아 있으면
청소해야 한다 — 이름은 맞는데 ✓ 만 굳는 사고가 그 경로다.

셸 쪽은 프롬프트마다 도니까 비용이 중요하다. `git rev-parse` 는 디렉토리별로
캐시하고, 이름이 이미 맞으면 `rename-window` 를 건너뛴다.
실측 5.6ms (평상시) / 18ms (이름 변경 시) / 14ms (`cd` 직후), WSL2 기준.

## 경로는 `$HOME` 으로 쓴다

훅 커맨드는 셸을 거쳐 실행되므로 `$HOME` 이 확장된다 (실측 확인).
설치 시점 경로 치환이 필요 없다. JSON 문자열 안이라 이스케이프가 붙는다:

```json
"command": "\"$HOME\"/.local/bin/agent-window-label ⏳ busy"
```

## Codex 만의 제약 — 신뢰 승인

Codex 는 비관리 훅에 **명시적 신뢰 검토**를 요구한다. 훅 정의의 sha256 을 저장해두고
바뀌면 다시 승인받는다. `/hooks` 로 검토·승인한다.

신뢰 상태의 키가 `<파일>:<이벤트>:<인덱스>:<인덱스>` 형태라서,
**배열 중간에 항목을 끼워넣으면 인덱스가 밀려 기존 훅의 신뢰가 깨진다.**
반드시 배열 끝에 append 한다. 자세한 절차는 `codex/README.md`.

## 훅이 안 도는 것 같을 때

1. `./install.sh --check` — 심링크가 끊겼나
2. JSON 문법 — 깨지면 그 파일의 설정이 **통째로** 무시된다
3. 매처가 도구 이름과 맞나 (`Bash` `Write` `Edit` …)
4. 커맨드를 직접 파이프해본다:
   `echo '{"cwd":"'$HOME'"}' | ~/.local/bin/agent-window-label ⏳ busy`
5. 설정을 바꿨는데 안 먹으면 세션이 리로드를 안 한 것 — `/hooks` 를 한 번 열었다 닫거나 재시작
6. Claude Code 는 훅이 느리거나 오류일 때만 "Ran N hooks" 를 띄운다.
   **조용한 성공과 조용한 실패가 구분되지 않는다.** 센티넬을 심어 확인한다:

```bash
tmux set -w -t "$TMUX_PANE" @cc PROBE   # 심고
# 아무 도구나 실행한 뒤
tmux show -w -t "$TMUX_PANE" -v @cc     # busy 로 바뀌었으면 훅이 돈 것
```

출처: `https://learn.chatgpt.com/docs/hooks` · Claude Code settings 스키마
