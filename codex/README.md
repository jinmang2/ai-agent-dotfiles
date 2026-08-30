# Codex CLI 설정

## 왜 여기엔 파일이 거의 없나

`~/.codex/` 의 대부분은 **oh-my-codex(OMX)가 생성한 것**이라 재설치로 복원된다.

| 항목 | 크기 | 성격 |
|---|---|---|
| `AGENTS.md` | 20.7KB | `<!-- omx:generated:agents-md -->` — OMX 생성 |
| `agents/*.toml` | 22개 | OMX 설치물 |
| `skills/` `prompts/` | 29 + 37 | OMX 설치물 |
| `config.toml` | 3.3KB | 절반이 훅 신뢰 해시 · 절대경로 · 프로젝트 trust — **기계 고유** |
| `auth.json` | 4.6KB | **OAuth 토큰 — 절대 커밋 금지** |

Claude 쪽 OMC와 같은 구조다. 프레임워크는 재설치하고, 우리 것만 들고 간다.

## 창 이름 훅 (적용됨 · 2026-08-30)

Codex 훅 형식은 Claude Code 의 `settings.json` `hooks` 와 **스키마가 동일**하다.
이벤트도 거의 1:1 대응한다.

| Claude Code | Codex | 상태 |
|---|---|---|
| `UserPromptSubmit` | `UserPromptSubmit` | ⏳ busy |
| `Notification` | `PermissionRequest` | ❓ waiting |
| `PostToolUse` | `PostToolUse` | ⏳ busy (복구) |
| `Stop` | `Stop` | ✅ done |

그래서 `agent/window-label.sh` 하나를 그대로 쓴다 (설치 위치 `~/.local/bin/agent-window-label`).
프로필만 다르다 — `profiles.conf` 의 `codex 🟠`.

### 적용 절차 (수동. 이유가 있다)

이 머신에는 적용돼 있다. 아래는 **새 머신에서 다시 할 때** 의 절차다.
`./install.sh --check` 가 적용 여부를 봐준다 — 안 붙어 있으면 `미적용` 로 뜬다.

`~/.codex/hooks.json` 에는 이미 OMX 훅 7개와 그 **신뢰 해시**가 들어있다.
Codex 는 비관리 훅을 `<파일>:<이벤트>:<인덱스>:<인덱스>` 키로 신뢰 상태를 추적하므로,
배열에 항목을 끼워넣으면 **인덱스가 밀려 기존 훅의 신뢰가 깨질 수 있다.**

1. 백업: `cp ~/.codex/hooks.json ~/.codex/hooks.json.bak`
2. `hooks.snippet.json` 의 각 이벤트를 `~/.codex/hooks.json` 의 `"hooks"` 객체에
   **배열 끝에 append** (기존 항목 앞에 넣지 말 것)
3. Codex 실행 후 `/hooks` — 새 훅을 검토하고 신뢰
4. OMX 훅 7개가 여전히 trusted 인지 같은 화면에서 확인

`AGENT_PROFILE=codex` 가 걸려 있어야 🟠 마커가 붙는다. `shell/agents.sh` 의 `codex()`
래퍼가 걸어준다 — 안 걸면 `window-label.sh` 의 기본값 `claude` 로 떨어져 Codex 창에
🔵(개인 Claude) 마커가 붙는다. 도구를 구분하려고 만든 표시가 거짓말을 하게 된다.

## 재설치

```bash
npm i -g @openai/codex          # codex-cli
npm i -g oh-my-codex && omx setup
codex                           # 실행 후 로그인
```

## 문서와 실제가 다른 점

공식 문서는 스킬 탐색 경로를 `$CWD/.agents/skills` → `$REPO_ROOT/.agents/skills`
→ `$HOME/.agents/skills` → `/etc/codex/skills` 로 안내한다.
그러나 이 머신에는 `~/.agents/skills` 가 없고 `~/.codex/skills` 에 29개가 있다.
OMX 가 `config.toml` 의 `[[skills.config]]` 로 경로를 지정하는 것으로 보인다.
새 머신에서 스킬이 안 잡히면 이 지점을 먼저 확인할 것.

출처: https://learn.chatgpt.com/docs/hooks · https://learn.chatgpt.com/docs/build-skills
