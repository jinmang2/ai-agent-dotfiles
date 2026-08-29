# 훅 레퍼런스 — Claude Code · Codex

이 저장소의 `claude/settings.json` 과 `codex/hooks.snippet.json` 을 읽고 고치는 데 필요한 것.
2026-08-29 기준 · Claude Code 2.1.251 · codex-cli 0.139.0.

## 두 도구의 훅 형식은 같다

```json
{"hooks": {"<이벤트>": [{"matcher": "<정규식>", "hooks": [
  {"type": "command", "command": "...", "timeout": 5, "async": true}
]}]}}
```

Claude Code 는 `~/.claude/settings.json` 안에, Codex 는 `~/.codex/hooks.json` 에 둔다.
그래서 `agent/window-label.sh` 하나를 양쪽에서 그대로 쓴다.

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

실측: 조기 탈출 8ms, 전체 렌더 21ms.

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
