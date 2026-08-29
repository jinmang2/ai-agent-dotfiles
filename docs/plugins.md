# 플러그인 · 마켓플레이스 — 직접 만들어 배포하기

`snflkd/fluent-korean` (별 984개) 을 전부 뜯어 확인한 내용. 저장소 전체가 6개 파일이고
**실제 기여물은 마크다운 2개(12KB)** 였다. 나머지는 JSON 1KB 와 README·LICENSE.

## 두 층은 분리돼 있다

**층 1 — 나만 쓰기: 파일 하나면 끝. 매니페스트 불필요.**

| 만들 것 | 두는 곳 |
|---|---|
| 출력 스타일 | `~/.claude/output-styles/<이름>.md` |
| 서브에이전트 | `~/.claude/agents/<이름>.md` |
| 슬래시 명령 | `~/.claude/commands/<이름>.md` |
| 스킬 | `~/.claude/skills/<이름>/SKILL.md` |

**층 2 — 남이 설치하게: JSON 2개 추가.**

```
저장소루트/
├── .claude-plugin/marketplace.json        ← 이 저장소가 배포하는 플러그인 목록
└── plugins/<플러그인명>/
    ├── .claude-plugin/plugin.json         ← 이 플러그인의 정체
    ├── agents/  commands/  output-styles/  skills/
    ├── hooks/hooks.json
    └── .mcp.json  .lsp.json  workflows/
```

같은 JSON 2개가 위 다섯 종류를 **전부** 커버한다. 한 플러그인에 여러 종류를 함께 넣어도
매니페스트는 그대로다.

## 두 매니페스트

| 파일 | 답하는 질문 | 필수 |
|---|---|---|
| `marketplace.json` (루트) | 이 저장소에 어떤 플러그인들이 있나 | `name`, `plugins[]` — 각 항목에 `name` + `source` |
| `plugin.json` (플러그인 폴더) | 이 플러그인은 무엇인가 | `name` **하나뿐** |

`plugin.json` 의 `version` `author` `license` `keywords` `repository` 는 전부 선택이다.
`source: "./plugins/<이름>"` 가 두 파일을 잇는 유일한 연결고리다.

경로를 바꾸고 싶으면 `plugin.json` 에 명시한다 (`"agents": ["./custom/agents/"]` 등).
생략하면 관례 디렉토리를 자동으로 찾는다.

## 설치하는 쪽

```
/plugin marketplace add <owner>/<repo>          저장소를 마켓플레이스로 등록
/plugin install <플러그인명>@<마켓플레이스명>
```

로컬 개발 중이면 `claude --plugin-dir ./plugins/<이름>` 으로 바로 붙여 시험한다.

## 이 저장소의 구조

```
.claude-plugin/marketplace.json
plugins/ai-agent-dotfiles/
  .claude-plugin/plugin.json
  agents/inspector.md
  output-styles/
```

`install.sh` 는 이것들을 `~/.claude/` 로 심링크한다 (마켓플레이스 등록 전에도 쓰기 위해).
푸시한 뒤에는 다른 머신에서 `/plugin install` 두 줄로 끝난다 — **심링크 끊김 문제 자체가
사라진다.**

`tmux.conf` `bashrc` `gitconfig` `agent/window-label.sh` 는 플러그인 콘텐츠가 아니라
`install.sh` 몫으로 남는다. 그래서 혼합 구조다.

## 배운 것

- 구조는 처음 한 번 짜면 끝이다. fluent-korean 도 매니페스트 2개를 첫날 만들고
  이후 15개 커밋은 전부 본문과 README 수정이었다.
- 진입 장벽은 형식이 아니라 **내용**이다. JSON 1KB 는 30분이면 쓰고,
  가치는 md 12KB 에 있다.
- 남의 것을 받아 쓰는 것과 직접 만드는 것의 기술적 격차는 거의 없다.
