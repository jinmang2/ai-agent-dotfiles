# 머신이 여러 대일 때

PC 가 늘어날 때 손대는 곳을 한 군데로 묶어두기 위한 규칙.

## 세 개의 서랍

설정을 셋 중 하나로 분류한다. 어디에 넣을지 헷갈리면 "새 머신에서 이 값이
**그대로** 맞나?" 를 묻는다.

| 서랍 | 두는 곳 | 예 |
|---|---|---|
| 공개해도 되는 공용 메커니즘 | 이 저장소 | 훅, `window-label.sh`, tmux, 공용 권한 규칙 |
| 머신 고유 값 | `local/hosts/<호스트>/` (비공개 서브모듈) | 절대경로가 든 권한, `autoMode` 환경 서술 |
| 재설치로 복원되는 것 | 아무 데도 안 둔다 | OMC/OMX/gstack 생성물, 플러그인 본체, `CLAUDE.md` |

## 호스트 이름

`hostname` 을 소문자로 바꾼 값이 디렉토리 이름이다.
WSL 처럼 호스트명이 바뀔 수 있으면 `AGENT_DOTFILES_HOST` 로 고정한다.

```
local/
  ssh-config              모든 머신이 공유 (tailnet 별칭표)
  hosts/
    <hostname>/
      settings-overlay.json
    <hostname>/
```

실제 호스트명은 비공개 서브모듈 안에만 있다. `ssh-config` 의 사람이 부르는 별칭과
`hosts/` 의 `hostname` 값은 같은 머신을 가리키는 두 이름이다.

## settings 오버레이

`~/.claude/settings.json` 은 **user 스코프 설정 파일이 하나뿐**이라
공용/고유를 파일로 나눌 수가 없다. 그래서 설치 시점에 합친다.

```
claude/settings.json                          공용
  + local/hosts/<호스트>/settings-overlay.json  이 머신만
  = ~/.claude/settings.json                   install.sh 가 생성
```

오버레이가 **없으면** `~/.claude/settings.json` 은 저장소 파일로 가는 심링크다
(그래서 `~/.claude` 에서 고치면 곧바로 저장소 변경으로 잡힌다).
오버레이가 **있으면** 실제 파일로 생성된다 — 이때는 `~/.claude/settings.json` 을
직접 고쳐도 다음 `./install.sh` 에서 덮어쓰인다. 고칠 곳은 둘 중 하나다:
공용이면 `claude/settings.json`, 이 머신만이면 오버레이.

`./install.sh --check` 가 어느 모드인지 알려준다.

### 병합 규칙

`scripts/merge-settings.py`. 항상 공용부터 다시 만들기 때문에 몇 번 돌려도 결과가 같다.

| 타입 | 규칙 |
|---|---|
| 객체 | 깊게 병합, 오버레이 키가 이김 |
| 배열 | 공용 + 오버레이 이어붙이고 중복 제거 |
| 스칼라 | 오버레이가 이김 |
| `null` | 그 키를 **삭제** — 공용 설정을 이 머신에서만 끄는 용도 |

배열이 이어붙기 때문에 `permissions.allow` 에 이 머신 전용 규칙을 더하는 게
가장 흔한 용법이다.

```json
{
  "permissions": { "allow": ["Bash(chmod +x /home/<나>/<그 머신에만 있는 저장소>/scripts/*)"] },
  "model": "opus[1m]"
}
```

## 새 머신을 추가할 때

1. `docs/checklist.md` 대로 세운다. 오버레이 없이도 전부 동작한다.
2. 그 머신에만 필요한 값이 생기면 그때 `local/hosts/$(hostname | tr 'A-Z' 'a-z')/settings-overlay.json`
   을 만들고 `./install.sh` 를 다시 돌린다.
3. `local/ssh-config` 에 tailnet 별칭 한 줄, `agent/profiles.conf` 에 계정이 늘었으면 한 줄.

## 계정을 추가할 때

`shell/agents.sh` 의 `CLAUDE_ACCOUNT_DIRS_<이름>` 한 줄이면 된다.
`claude-<이름>` 실행 함수와 `claude-accounts` 목록은 그 변수를 훑어 자동으로 생긴다.
`agent/profiles.conf` 에 `claude-<이름> <마커>` 를 더하면 tmux 창에서도 구분된다.

## 회사 머신에서 주의할 것

- `codex/config.template.toml` 은 `approval_policy` · `sandbox_mode` · `network_access`
  를 **일부러 담지 않는다.** 개인 머신의 느슨한 값이 설정 파일을 타고 조용히
  들어가면 안 되기 때문이다. 필요하면 그 머신에서 명시적으로 추가한다.
- `local/` 은 비공개 저장소다. 회사 머신 고유 값(내부 호스트명 등)을 넣기 전에
  그 정보를 개인 GitHub 비공개 저장소에 두어도 되는지 먼저 확인한다.
  안 되면 그 머신에서는 오버레이를 저장소 밖에 두고 `install.sh` 를 쓰지 않는다.
