# 스킬 — Claude Code · Codex

## 형식은 사실상 같다

```
<스킬이름>/
  SKILL.md          필수. frontmatter + 본문
  scripts/          선택. 실행 코드
  references/       선택. 참고 문서
  assets/           선택. 템플릿
```

```markdown
---
name: skill-name
description: 언제 이 스킬이 걸리는지. 모델은 이 문장만 먼저 읽고 선택한다.
---

본문. 선택된 뒤에야 로드된다 (progressive disclosure).
```

`description` 이 전부다. 본문이 아무리 좋아도 여기서 안 걸리면 안 불린다.
**무엇을 하는지가 아니라 언제 쓰는지**를 쓴다.

## 탐색 경로

| 도구 | 경로 |
|---|---|
| Claude Code | `<프로젝트>/.claude/skills/` → `~/.claude/skills/` → 플러그인 |
| Codex | `$CWD/.agents/skills` → `$REPO_ROOT/.agents/skills` → `$HOME/.agents/skills` → `/etc/codex/skills` |

**주의**: 두 경로가 동시에 쓰인다. 공식 경로인 `~/.agents/skills` 에는 에이전트
공통 스킬(`skills` CLI 가 `~/.agents/.skill-lock.json` 으로 관리)이 들어가고,
OMX 가 설치한 것은 `~/.codex/skills` 에 들어간다 — `config.toml` 의
`[[skills.config]]` 로 경로를 지정하기 때문으로 보인다.
스킬이 안 잡히면 두 곳을 다 본다.

`~/.agents/skills` 는 여러 에이전트(codex, gemini-cli, copilot, cursor, …)가
공유하는 자리라 도구를 늘릴수록 값어치가 커진다. 복원은 `.skill-lock.json` 의
`sourceUrl` 을 보고 다시 설치하면 된다. 잠금 파일에 없는 스킬은 손으로 넣은 것이므로
출처를 따로 적어두지 않으면 새 머신에서 복원할 수 없다.

## 프로젝트 스킬 vs 전역 스킬

| | 두는 곳 |
|---|---|
| 그 저장소에서만 의미 있음 (빌드 절차, 그 코드베이스의 함정) | 프로젝트 `.claude/skills/` |
| 어디서나 쓰는 절차 | `~/.claude/skills/` |

프로젝트 스킬은 **프로젝트 저장소에 커밋한다.** 이 dotfiles 저장소로 끌어오지 않는다.
같이 일하는 사람도 받아야 하고, 그 코드와 수명이 같기 때문이다.

## 스킬 · 서브에이전트 · 슬래시 명령

| | 무엇 |
|---|---|
| 스킬 | 절차 지식. 모델이 필요할 때 자동으로 끌어씀 |
| 서브에이전트 | 격리된 실행 단위. 자기 컨텍스트를 가짐 |
| 슬래시 명령 | 사용자가 명시적으로 부르는 것. `~/.claude/commands/<이름>.md` |

같은 일을 셋 다로 만들 수 있다. 기준은 **누가 언제 부르는가**다.
모델이 알아서 → 스킬. 내가 직접 → 슬래시 명령. 격리해서 여러 개 → 서브에이전트.
