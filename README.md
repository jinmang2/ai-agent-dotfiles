# ai-agent-dotfiles

Claude Code · Codex CLI · Gemini · tmux · 셸 설정. 새 머신에서 `clone` + `install.sh` 로 선다.

목표는 설정 보관이 아니라 **내 것과 남의 것의 경계를 아는 것**이다.

프레임워크(OMC · superpowers · gstack …)는 계속 쓴다 — 실제로 플러그인 6개를 켜둔다.
다만 그것들이 훅·스킬·서브에이전트·마켓플레이스로 *무엇을 하고 있는지* 알고 쓰고,
재설치로 복원되는 것과 내가 만든 것을 섞지 않는다. 그래서 이 저장소는 작다.
저장소에 든 건 대부분 프레임워크가 안 해주는 것들이다 — 창 이름, 다중 계정,
머신별 설정 병합.

머신이 여러 대라는 걸 전제로 한다. 공용 메커니즘은 이 저장소에, 머신 고유 값은
비공개 서브모듈의 `local/hosts/<호스트>/` 에 둔다 — `docs/machines.md`.

## 설치

### 플러그인만 (서브에이전트 등)

```
/plugin marketplace add jinmang2/ai-agent-dotfiles
/plugin install ai-agent-dotfiles@ai-agent-dotfiles
```

### 전체 (훅 · tmux · 셸까지)

```bash
gh auth login          # 먼저. 비공개 서브모듈이 이걸 탄다
git clone --recursive https://github.com/jinmang2/ai-agent-dotfiles ~/ai-agent-dotfiles
cd ~/ai-agent-dotfiles && ./install.sh
source ~/.bashrc
```

`./install.sh --check` 로 링크 상태만 점검. 몇 번 돌려도 안전하고, 덮어쓰기 전에
기존 파일을 `.pre-install-<타임스탬프>` 로 백업한다.

그 다음 `claude` 를 한 번 실행하면 플러그인이 자동으로 깔린다 —
`settings.json` 에 마켓플레이스와 활성 플러그인이 적혀 있다.

## 구조

```
agent/          두 도구가 공유하는 것
  window-label.sh    tmux 창 이름 (Claude·Codex 공용)
  profiles.conf      프로필 → 마커 표
claude/         Claude Code 전용
  settings.json      훅 8개 · 권한 · 플러그인 6개 · 스테이터스라인
plugins/ai-agent-dotfiles/     배포 단위 (마켓플레이스로 설치됨)
  .claude-plugin/plugin.json
  agents/inspector.md
codex/          Codex CLI 전용
  config.template.toml   이식 가능한 부분만
  hooks.snippet.json     창 이름 훅 (준비됨, 미적용)
  README.md              적용 절차와 신뢰 모델
gemini/GEMINI.md
tmux/tmux.conf
shell/
  agents.sh          다중 계정 · ccname · 창 이름(셸 쪽)
  aliases.sh         ll · gpuw · t
  bashrc.snippet     .bashrc 에 들어가는 블록
scripts/
  merge-settings.py       공용 settings + 머신 오버레이 병합
  test-merge-settings.py  그 병합 규칙의 테스트 (22개)
docs/           레퍼런스
  hooks.md · skills.md · subagents.md · plugins.md · machines.md · checklist.md
local/          비공개 서브모듈 (jinmang2/ai-agent-dotfiles-local)
  ssh-config           tailnet 별칭 (전 머신 공용)
  hosts/<호스트>/       이 머신에서만 쓰는 값
```

설치되는 위치:

| 저장소 | → | 설치 위치 |
|---|---|---|
| `agent/window-label.sh` | 심링크 | `~/.local/bin/agent-window-label` |
| `agent/profiles.conf` | 심링크 | `~/.config/agent-profiles.conf` |
| `shell/agents.sh` | 심링크 | `~/.config/agent-dotfiles/agents.sh` |
| `shell/aliases.sh` | 심링크 | `~/.config/agent-dotfiles/aliases.sh` |
| `tmux/tmux.conf` | 심링크 | `~/.tmux.conf` |
| `gemini/GEMINI.md` | 심링크 | `~/.gemini/GEMINI.md` |
| `claude/settings.json` | 심링크 **또는 병합** | `~/.claude/settings.json` |
| `plugins/ai-agent-dotfiles/` | 마켓플레이스 | Claude Code 가 직접 설치 |
| `local/ssh-config` | 없을 때만 복사 (600) | `~/.ssh/config` |

공용 항목은 일부러 `~/.claude/` 밖에 둔다. Codex 도 같은 스크립트를 쓴다.

서브에이전트는 **심링크하지 않는다.** 플러그인 하나만이 배포 경로다 —
두 경로로 들어와 중복되던 걸 정리했다 (`docs/plugins.md`).

`~/.ssh/config` 도 심링크하지 않는다. 600 권한이 필요하고 도구들이 직접 고치기도 한다.
없을 때만 복사하고, 이미 있으면 **손대지 않고 차이만 보여준다** — ssh 설정은 잘못
덮어쓰면 접속 자체가 막힌다.

## 머신 고유 설정

Claude Code 의 user 스코프 설정 파일은 `~/.claude/settings.json` **하나뿐이다.**
(`~/.claude/settings.local.json` 은 만들어도 무시된다 — 프로젝트 스코프에만 있다.)
그래서 파일을 나누는 대신 설치 시점에 합친다.

```
claude/settings.json                            공용
  + local/hosts/<호스트>/settings-overlay.json    이 머신만
  = ~/.claude/settings.json
```

오버레이가 없으면 그냥 심링크다. 자세한 병합 규칙과 새 머신 추가 절차는
`docs/machines.md`.

## tmux 창 이름

```
1:myrepo          이모지 없음 = 셸.  cd 하면 따라간다
2:~/dl
3:⏳🔵myrepo       이모지 있음 = 그 창에 에이전트가 살아있다
4:❓🟠client-api

⏳ 작업중  ❓ 입력대기  ✅ 완료   /   🔵 claude  🟣 claude-team  🟠 codex
```

**주인이 둘이다.** 에이전트가 창을 점유하면 훅이 이름을 쥐고, 셸로 돌아오면
`PROMPT_COMMAND` 가 쥔다. 프롬프트는 전경 프로그램이 없을 때만 그려지므로
둘이 겹치지 않는다.

이 구조가 필요한 이유: **에이전트가 창을 떠났다는 이벤트가 없다.** Claude Code 의
`Stop` 훅은 턴 끝에 불릴 뿐이고 강제 종료되면 아무 훅도 안 불린다. 예전엔 종료
후에도 `✅🔵myrepo` 가 그대로 굳었다. 지금은 셸 프롬프트가 그려지는 순간 이모지가
빠진다 — 그래서 **이모지 유무가 에이전트 생존 여부를 뜻하게 됐다.**

라벨 우선순위는 수동 작업명 > git 저장소 이름 > `~` > 디렉토리 이름.
브랜치는 일부러 안 쓴다 (수시로 바뀌어 식별에 도움이 안 된다).
Claude Code 안에서 `!ccname 결제-마이그레이션` 으로 작업명을 고정, `!ccname --clear` 로 해제.

`.tmux.conf` 의 `automatic-rename off` 가 없으면 tmux 가 창 이름을 계속 덮어쓴다.
tmux 설정과 훅과 셸은 이 지점에서 결합돼 있다.

비용은 프롬프트당 5.6ms (이름이 이미 맞을 때), 바꿔야 하면 18ms. git 호출은
디렉토리별로 캐시해 한 번만 돈다. SSH 로 다른 머신에 들어간 창은 원격 셸이라
로컬 tmux 이름을 못 바꾼다 — 알려진 한계다.

## 명령

| 명령 | 하는 일 |
|---|---|
| `t` | tmux 세션 진입. 인자 없으면 목록에서 고르고, 없으면 저장소 이름으로 생성 |
| `t <이름>` | 그 이름으로 붙거나 만든다 |
| `ll` | `ls -alFh --color=auto --group-directories-first` |
| `gpuw` | `watch -n1 nvidia-smi` |
| `claude-accounts` | 계정별 로그인 / 공유 링크 상태 |
| `claude-account-link team` | 끊긴 공유 링크 복구 |
| `claude-team` | team 계정으로 Claude Code 실행 |
| `ccname <작업명>` | 창 작업명 고정 (`--clear` 해제) |
| `./install.sh --check` | 저장소 ↔ 설치 위치 점검. 어긋나면 무엇이 달라지는지 diff 출력 |
| `python3 scripts/test-merge-settings.py` | settings 병합 규칙 테스트 |

## 다중 계정

계정마다 `CLAUDE_CONFIG_DIR` 를 분리하되 `skills/ plugins/ settings.json hooks/ hud/` 는
`~/.claude` 것을 심링크로 공유한다. 계정당 추가 디스크 약 4KB.

계정을 늘리려면 `shell/agents.sh` 의 `CLAUDE_ACCOUNT_DIRS_<이름>` **한 줄**이면 된다.
`claude-<이름>` 실행 함수와 `claude-accounts` 목록은 자동으로 따라온다.
tmux 에서 구분하려면 `agent/profiles.conf` 에 마커 한 줄을 더한다.

## 저장소에 없는 것

| 제외 | 이유 |
|---|---|
| `~/.claude/.credentials.json` · `~/.codex/auth.json` | OAuth 토큰 |
| `projects/ sessions/ history.jsonl` | 대화 기록 전문 |
| `~/.claude/skills/` (1.5G) · `plugins/` (634M) | 재설치로 복원 |
| `~/.claude/hud/` | OMC 설치물. **`settings.json` 의 statusLine 이 이걸 참조한다** |
| `~/.claude/CLAUDE.md` | OMC 생성물. `omc setup` 이 덮어쓴다 |
| `~/.codex/AGENTS.md` · `agents/` · `skills/` | OMX 생성물 |
| `config.toml` 의 절대경로 · 프로젝트 trust · 훅 해시 | 기계 고유 |
| `config.toml` 의 `sandbox_mode` · `approval_policy` | 보안 태세. 머신마다 직접 정한다 |
| `~/.gitconfig` | `gh auth` 가 수시로 다시 써서 심링크가 끊긴다 |

## 새 머신 복원

`docs/checklist.md` 에 순서대로 있다. 요약:

```bash
gh auth login && git clone --recursive ... && ./install.sh   # 설정
claude                                                        # 플러그인 자동 설치 + /login
npm i -g @openai/codex oh-my-codex && omx setup               # Codex (선택)
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack   # 선택
```

`settings.json` 은 저장소에 없는 두 가지를 참조한다. 둘 다 조용히 실패하므로 미리 알아둔다.

| 참조 | 없으면 | 복원 |
|---|---|---|
| `~/.claude/skills/gstack/...` (훅 3개) | `AskUserQuestion` 훅만 실패 | gstack clone |
| `~/.claude/hud/omc-hud-cache.sh` (statusLine) | 스테이터스라인이 빈 줄 | `omc setup` |

`omc setup` 은 `claude` 를 한 번 띄워 OMC 플러그인이 깔린 뒤에 돈다. 그전까지는
statusLine 이 비어 보이는 게 정상이다.

## 함정

- **심링크가 끊길 수 있다.** 설정을 원자적으로 쓰는 코드 경로를 만나면 심링크가 실제
  파일로 바뀌어 저장소 추적이 조용히 끊긴다. `./install.sh --check` 로 잡고
  `./install.sh` 로 복구한다. 기존 내용은 `.pre-install-<타임스탬프>` 로 보존된다.
- **오버레이가 있으면 `~/.claude/settings.json` 은 생성물이다.** 거기서 직접 고치면
  다음 `./install.sh` 에 덮어쓰인다. 공용이면 `claude/settings.json`, 이 머신만이면
  오버레이를 고친다. Claude Code 가 "Yes, and don't ask again" 으로 거기에 직접
  쓰는 경우도 있으니, `--check` 와 설치 시점에 **무엇이 사라지는지 diff 로 보여준다.**
  이미 병합 결과와 같으면 다시 쓰지 않는다 (백업 파일이 쌓이지 않도록).
- **`~/.claude/settings.local.json` 은 읽히지 않는다.** user 스코프엔 그런 파일이 없다.
  도구용 환경변수는 `shell/agents.sh` 에서 export 한다.
- **셸 함수는 대화형 셸에서만 산다.** `.bashrc` 는 비대화형이면 앞부분에서 `return` 한다.
  새 창을 열거나 `source ~/.bashrc`. 창 이름도 같은 이유로 대화형 셸에서만 갱신된다.
- **`.bashrc` 블록은 통째로 갈아끼워진다.** `# >>> ai-agent-dotfiles >>>` 와
  `# <<<` 사이는 `install.sh` 소유다. 거기에 직접 쓴 건 다음 설치에 사라진다.
- **alias 가 함수를 가린다.** 예전에 손으로 넣은 `alias claude-team=...` 이 남아 있으면
  `agents.sh` 의 함수 대신 그게 잡힌다. `install.sh` 가 찾아서 주석 처리한다.
- **Codex 훅은 신뢰 승인이 필요하다.** `~/.codex/hooks.json` 배열에 항목을 끼워넣으면
  인덱스가 밀려 기존 훅의 신뢰가 깨질 수 있다. `codex/README.md` 참고.
