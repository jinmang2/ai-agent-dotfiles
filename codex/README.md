# Codex CLI 설정

## 왜 여기엔 파일이 거의 없나

`~/.codex/` 의 대부분은 **oh-my-codex(OMX)가 생성한 것**이라 재설치로 복원된다.

| 항목 | 성격 |
|---|---|
| `AGENTS.md` | `<!-- omx:generated:agents-md -->` — OMX 생성 |
| `agents/*.toml` | OMX 설치물 |
| `skills/` `prompts/` | OMX/플러그인/로컬 설치물. 개수는 설치 상태에 따라 변함 |
| `config.toml` | 훅 신뢰 상태 · 절대경로 · 프로젝트 trust 포함 — **기계 고유** |
| `auth.json` | **OAuth 토큰 — 절대 커밋 금지** |

Claude 쪽 OMC와 같은 구조다. 프레임워크는 재설치하고, 우리 것만 들고 간다.

## 창 이름 훅

Codex 훅 형식은 Claude Code 의 `settings.json` `hooks` 와 **스키마가 동일**하다.
이벤트도 거의 1:1 대응한다.

| Claude Code | Codex | 상태 |
|---|---|---|
| `UserPromptSubmit` | `UserPromptSubmit` | » busy |
| `Notification` | `PermissionRequest` | ? waiting |
| `PostToolUse` | `PostToolUse` | » busy (복구) |
| `Stop` | `Stop` | ✓ done |

그래서 `agent/window-label.sh` 하나를 그대로 쓴다 (설치 위치 `~/.local/bin/agent-window-label`).
프로필만 다르다 — `profiles.conf` 의 `codex colour208`(주황).

### 적용 절차

이 머신에는 적용돼 있다. 아래는 **새 머신에서 다시 할 때** 의 절차다.
`scripts/codex-wiring.py` 가 적용 여부를 봐준다.

`~/.codex/hooks.json` 에는 훅 정의만 둔다. 훅 신뢰 상태의 정본은
`~/.codex/config.toml` 의 `[hooks.state."..."]` 이다. Codex 는 비관리 훅을
`<파일>:<이벤트>:<인덱스>:<인덱스>` 키로 추적하므로, 배열 앞에 항목을 끼워넣으면
기존 훅의 신뢰 상태가 어긋날 수 있다.

0. **최상위 키를 먼저 본다.** codex 는 `description` 과 `hooks` 만 받는다.
   옛 버전이 남긴 `state`(신뢰 해시)가 최상위에 있으면 **파일 전체가 조용히 무시된다** —
   훅이 하나도 안 돈다. 실제로 그 상태로 얼마간 돌고 있었고, `/hooks` 화면을 열기
   전까지 아무도 몰랐다. 신뢰 상태의 정본은 `config.toml` 의 `[hooks.state."..."]` 이므로
   hooks.json 쪽 `state` 는 지워도 된다. `./install.sh --check` 가 이걸 본다.
1. 검사: `python3 scripts/codex-wiring.py --check --live --workflow-owner omx`
2. 적용: `python3 scripts/codex-wiring.py --apply --live --workflow-owner omx`
   기존 `config.toml` 과 `hooks.json` 은 쓰기 전에 `0600` 백업을 만든다.
   이 명령이 live Codex 설정을 실제로 바꾼다.
3. Codex 실행 후 `/hooks` — 새 훅을 검토하고 신뢰한다. 신뢰 해시는 Codex 가 계산한
   currentHash 를 사용해야 하며, dotfiles 스크립트가 합성하지 않는다.
4. 같은 화면에서 기존 훅이 필요한 상태로 남아 있는지 확인한다.

`./install.sh` 는 Codex 설정 파일을 직접 병합하지 않는다. 심링크 설치와 정적 검사를 하고,
Codex 배선이 다르면 위 `codex-wiring.py --apply --live --workflow-owner omx` 명령을 안내한다.

`AGENT_PROFILE=codex` 가 걸려 있어야 창 번호가 주황 배경이 된다. `shell/agents.sh` 의
`codex()` 래퍼가 걸어준다 — 안 걸면 `window-label.sh` 의 기본값 `claude` 로 떨어져
Codex 창 번호가 파랑(개인 Claude)이 된다. 도구를 구분하려고 만든 표시가 거짓말을 하게 된다.

## 상태줄과 companion HUD

**현재 한계 (2026-09-08):** 기존 세션에서는 고정줄을 확인했지만, 사용자가 새 세션에서
HUD가 아예 나타나지 않는다고 보고했다. 자동 적용은 미해결이며 아래 실행 경로 설명은
설계와 격리 시험 결과이지 모든 실제 진입 경로의 성공 보장이 아니다.
F8 단일키와 핵심 정보 상시 표시 확대는 추천만 했고 적용하지 않았다.
구현 내역·검증 범위·후속 확인 항목은 [변경 기록](../docs/codex-changes.md)을 참고한다.

`/statusline` — codex 안에서 치면 검색되는 체크박스 목록이 뜬다. 고를 수 있는 항목이
버전에 따라 달라지므로 숫자를 문서에 고정하지 않는다. `estimated-thread-cost` 처럼
쓸 만한 항목은 직접 검색해서 고른다.

`terminal_title` 도 같은 방식으로 `/terminal-title` 에서 고른다.

**여러 줄은 안 된다.** Claude Code 의 statusLine 은 `{type:"command"}` 라 스크립트가
찍는 걸 그대로 쓰지만(OMC HUD 가 여러 줄인 이유), codex 의 `[tui] status_line` 은
내장 항목 배열이다. 줄 수를 늘리는 옵션이 없다. 좁은 터미널에서는 항목을 줄이는 게
유일한 답이다 — 고른 값과 이유는 `config.template.toml` 의 `[tui]` 주석에 있다.

컨텍스트·사용량 한도는 Codex native footer 가 정본이다. 보조 HUD는 별도 pane 없이
기존 tmux 탭 목록 위의 고정 상태줄에 표시한다. 상세 정보는 **Alt+a → h**로 열고
**q**로 닫는다. 팝업은 방향키/PageUp/PageDown으로 스크롤할 수 있다.

최신 셸 함수가 입력 전에 pane을 등록하고, `SessionStart` 훅이 첫 메시지 처리 시
정확한 세션을 연결한다. 연결 전에는 같은 저장소의 다른 세션 값을 가져오지 않는다.
`SessionEnd`는 등록만 정리한다. 기존 분할 HUD는 소유권이 확인된 것만 제거한다. 끄려면:

```bash
CODEX_HUD=0 codex
```

한 번만 보거나 기계가 읽게 할 때는 직접 실행한다.

```bash
agent-codex-hud --detail --pane "$TMUX_PANE"
agent-codex-hud --json --pane "$TMUX_PANE"
```

`exec`, `doctor`, `app-server`, `mcp` 같은 비대화형 하위 명령은 companion HUD 를 띄우지 않는다.

## agentic-memory

Codex 쪽 메모리 배선은 `~/.local/bin/agent-memory-hook` 래퍼만 호출한다. 래퍼가
`AGMEM_CONFIG`, `AGMEM_NAMESPACE=main`, `AGMEM_HOOK_SOURCE=codex`, 공용 데몬 주소,
Python 경로, 내부 HTTP budget 을 소유한다. Codex native hook timeout 은
recall/recall_prompt 6초, capture 6초, preserve 30초, SessionEnd distill 3초다.
래퍼 내부 HTTP budget 은 distill 1.5초, 나머지 기본 5초다. capture 는 명령 인자가 아니라
native hook JSON 의 `async: true` 로 비동기 실행한다.

namespace 는 서버 기본값과 wrapper 기본값이 모두 `main` 이지만, HTTP MCP 요청마다
별도 namespace 를 명시한다는 뜻은 아니다. 시험 데이터를 실제 `main` 기억에 섞지 말 것.
hook/config 변경 뒤에는 기존 Codex 프로세스가 아니라 새 프로세스로 확인한다.

MCP 서버는 같은 HTTP 데몬을 사용한다.

```toml
[mcp_servers.agentic_memory]
url = "http://127.0.0.1:8765/mcp"
startup_timeout_sec = 30
tool_timeout_sec = 60
required = false
```

## 재설치

```bash
npm i -g @openai/codex          # codex-cli
npm i -g oh-my-codex && omx setup
codex                           # 실행 후 로그인
```

## 문서와 실제가 다른 점

공식 문서는 스킬 탐색 경로를 `$CWD/.agents/skills` → `$REPO_ROOT/.agents/skills`
→ `$HOME/.agents/skills` → `/etc/codex/skills` 로 안내한다.
이 머신에는 `~/.agents/skills` 도 있고, OMX/플러그인 쪽 `~/.codex/skills` 도 있다.
설치물 개수는 계속 변하므로 숫자로 판단하지 않는다. 새 머신에서 스킬이 안 잡히면
`config.toml` 의 `[[skills.config]]` 와 실제 두 경로를 같이 본다.

출처: https://learn.chatgpt.com/docs/hooks · https://learn.chatgpt.com/docs/build-skills
