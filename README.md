# ai-agent-dotfiles

Claude Code · Codex CLI · tmux · 셸 설정. 새 머신에서 `clone` + `install.sh` 로 선다.

목표는 설정 보관이 아니라 **프레임워크(OMC/OMX)에 기대지 않고 직접 다루는 것**이다.
훅·스킬·서브에이전트·마켓플레이스를 해체해서 실제로 쓰는 부분만 내 것으로 가져간다.

## 설치

### 플러그인만 (서브에이전트 등)

```
/plugin marketplace add jinmang2/ai-agent-dotfiles
/plugin install ai-agent-dotfiles@ai-agent-dotfiles
```

### 전체 (훅 · tmux · 셸까지)

```bash
git clone https://github.com/jinmang2/ai-agent-dotfiles ~/ai-agent-dotfiles
cd ~/ai-agent-dotfiles && ./install.sh
source ~/.bashrc
```

`./install.sh --check` 로 링크 상태만 점검. 심링크라서 `~/.claude` 나 `~/.tmux.conf` 를
고치면 곧바로 이 저장소의 변경으로 잡힌다. 몇 번 돌려도 안전하다.

## 구조

```
agent/          두 도구가 공유하는 것
  window-label.sh    tmux 창 이름 (Claude·Codex 공용)
  profiles.conf      프로필 → 마커 표
claude/         Claude Code 전용
  settings.json      훅 8개 · 권한 · 플러그인 · 스테이터스라인
plugins/ai-agent-dotfiles/     배포 단위
  .claude-plugin/plugin.json
  agents/inspector.md
codex/          Codex CLI 전용
  config.template.toml   이식 가능한 부분만
  hooks.snippet.json     창 이름 훅 (준비됨, 미적용)
  README.md              적용 절차와 신뢰 모델
tmux/tmux.conf
shell/          agents.sh · bashrc.snippet
docs/           레퍼런스
  hooks.md · skills.md · subagents.md · checklist.md
local/          이 머신 고유 (비공개 서브모듈, 커밋 안 됨)
```

설치되는 위치:

| 저장소 | → | 설치 위치 |
|---|---|---|
| `agent/window-label.sh` | | `~/.local/bin/agent-window-label` |
| `agent/profiles.conf` | | `~/.config/agent-profiles.conf` |
| `shell/agents.sh` | | `~/.config/agent-dotfiles/agents.sh` |
| `claude/settings.json` | | `~/.claude/settings.json` |
| `tmux/tmux.conf` | | `~/.tmux.conf` |

공용 항목은 일부러 `~/.claude/` 밖에 둔다. Codex 도 같은 스크립트를 쓴다.

## tmux 창 이름

```
⏳🔵myrepo        ⏳ 작업중  ❓ 입력대기  ✅ 완료
⏳🟣client-api    🔵 claude  🟣 claude-team  🟠 codex
⏳🟠client-api
```

Claude Code 안에서 `!ccname 결제-마이그레이션` 으로 작업명을 고정, `!ccname --clear` 로 해제.
라벨 우선순위는 수동 작업명 > git 저장소 이름 > `~` > 디렉토리 이름. 브랜치는 일부러 안 쓴다.

`.tmux.conf` 의 `automatic-rename off` 가 없으면 tmux 가 창 이름을 계속 덮어쓴다.
tmux 설정과 훅은 이 지점에서 결합돼 있다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `claude-accounts` | 계정별 로그인 / 공유 링크 상태 |
| `claude-account-link team` | 끊긴 공유 링크 복구 |
| `claude-team` | team 계정으로 Claude Code 실행 |
| `ccname <작업명>` | 창 작업명 고정 (`--clear` 해제) |
| `./install.sh --check` | 저장소 ↔ 설치 위치 링크 점검 |

## 다중 계정

계정마다 `CLAUDE_CONFIG_DIR` 를 분리하되 `skills/ plugins/ settings.json hooks/ hud/` 는
`~/.claude` 것을 심링크로 공유한다. 계정당 추가 디스크 약 4KB.

계정을 늘리려면 `shell/agents.sh` 의 `CLAUDE_ACCOUNT_DIRS_<이름>` 과
`agent/profiles.conf` 에 각각 한 줄씩.

## 저장소에 없는 것

| 제외 | 이유 |
|---|---|
| `~/.claude/.credentials.json` · `~/.codex/auth.json` | OAuth 토큰 |
| `projects/ sessions/ history.jsonl` | 대화 기록 전문 |
| `~/.claude/skills/` (1.5G) · `plugins/` (460M) | 재설치로 복원 |
| `~/.codex/AGENTS.md` · `agents/` · `skills/` | OMX 생성물 |
| `config.toml` 의 절대경로 · 프로젝트 trust · 훅 해시 | 기계 고유 |

## 새 머신 복원

```bash
./install.sh                                   # 설정 배치
claude                                         # 플러그인 자동 설치 + /login
npm i -g @openai/codex oh-my-codex && omx setup   # Codex (선택)
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack   # 선택
```

gstack 이 없으면 `settings.json` 의 `AskUserQuestion` 훅 3개만 조용히 실패한다.
나머지 기능엔 영향 없다.

## 함정

- **심링크가 끊길 수 있다.** 설정을 원자적으로 쓰는 코드 경로를 만나면 심링크가 실제
  파일로 바뀌어 저장소 추적이 조용히 끊긴다. `./install.sh --check` 로 잡고
  `./install.sh` 로 복구한다. 기존 내용은 `.pre-install-<타임스탬프>` 로 보존된다.
- **셸 함수는 대화형 셸에서만 산다.** `.bashrc` 는 비대화형이면 앞부분에서 `return` 한다.
  새 창을 열거나 `source ~/.bashrc`.
- **Codex 훅은 신뢰 승인이 필요하다.** `~/.codex/hooks.json` 배열에 항목을 끼워넣으면
  인덱스가 밀려 기존 훅의 신뢰가 깨질 수 있다. `codex/README.md` 참고.
