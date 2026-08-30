# OMC (oh-my-claudecode) — 무엇이 깔려 있고 무엇이 실제로 도나

`~/.claude/CLAUDE.md` 를 쓰는 주체이자 훅 25개 · MCP 도구 55개(기본 등록)를 얹는 플러그인.
이 저장소가 관리하지 않는 설치물이지만, `settings.json` 의 statusLine 과 `install.sh` 의
HUD 블록이 여기에 의존한다. 2026-08-30 기준 · OMC 5.0.2.

## 설치 지점이 둘이다

| | 무엇 | 갱신 |
|---|---|---|
| 플러그인 | `~/.claude/plugins/cache/omc/oh-my-claudecode/<버전>/` | `claude plugin update oh-my-claudecode@omc` (재시작 필요) |
| `omc` CLI | npm 전역 `oh-my-claude-sisyphus` | `npm i -g oh-my-claude-sisyphus@<버전>` |

**둘은 따로 논다.** 플러그인만 올리면 CLI 가 4.x 로 남아 `omc setup` 이 옛 CLAUDE.md 를
쓴다. 버전을 맞춘 뒤 `omc setup` 을 돌려야 `CLAUDE.md` · HUD 가 새 버전과 같아진다.

`omc setup` 은 `~/.claude/settings.json` 을 **끝 줄바꿈 없이** 다시 쓴다. 내용은 같지만
`install.sh --check` 는 정확한 텍스트 비교라 그 뒤로 계속 `갱신필요` 가 뜬다.
`./install.sh` 로 되돌리면 된다.

## 4.15.10 → 5.0.0 에서 사라진 것

별칭 없이 삭제됐다. 예전 이름은 그냥 안 걸린다.

```
ultrawork · ultraqa · ultrapilot · swarm · pipeline · merge-readiness
deep-dive · sciomc · ccg · omc-teams · setup · mcp-setup · omc-reference
learner · writer-memory · local-build-reminder
```

정식 워크플로는 `plan → execute → review → verify` 넷이고 나머지는 여기로 route 된다.

```
autopilot · ralph · ultragoal        →  execute
deep-dive · sciomc · autoresearch    →  research
merge-readiness                      →  review
```

`review` 는 Claude Code 기본 명령과 겹쳐서 **`omc-review`** 로 설치된다 (`plan` → `omc-plan` 과 같다).

## 스킬을 읽을 때

`skills/<이름>/SKILL.md` 는 **shim** 이다. 실제 지시문은 `skill-bodies/<이름>/SKILL.md` 에 있다.
frontmatter 의 `omc-full-body` 가 그 경로를 가리킨다. 모르고 읽으면 껍데기만 본다.

## 훅 25개

| 언제 | 개수 | 무거운 것 |
|---|---|---|
| UserPromptSubmit (매 프롬프트) | 2 | `keyword-detector` 1995줄/82KB, `skill-injector` |
| PreToolUse (매 도구호출) | 1 | `pre-tool-enforcer` 1975줄/85KB |
| PostToolUse (매 도구호출) | 3 | `post-tool-verifier` 1104줄, +메모리·룰 주입 |
| SessionStart | 5 | `session-start` 1320줄 |
| Stop | 4 | `persistent-mode` 1648줄, `workflow-drift-guard` 932줄 |
| PreCompact / SessionEnd / Subagent / PostToolUseFailure / PermissionRequest | 10 | 대부분 dist 위임 wrapper |

**도구를 한 번 부를 때마다 훅 4개(Pre 1 + Post 3)가 돈다.** 실행기 `run.cjs` 가
`keyword-detector` 8초 · `skill-injector` 12초로 별도 캡을 건다.

Stop 훅 넷은 턴을 **막을 수 있다** — `context-guard-stop` 은 컨텍스트가 임계치를 넘으면
`/compact` 를 권하며 최대 2회 차단, `workflow-drift-guard` 는 거짓 완료 주장(TODO·skip 테스트
잔존)을 감지해 차단, `persistent-mode` 는 ralph/autopilot 미완료면 다음 반복을 주입한다.

끄는 법:

```bash
DISABLE_OMC=1                                  # 전부
OMC_SKIP_HOOKS=keyword-detector,post-tool-use  # 골라서
```

스크립트마다 편차가 있다 — `DISABLE_OMC=true` 를 인정하는 것과 `=1` 만 보는 것이 섞여 있고,
`context-guard-stop` 등 일부는 두 변수를 아예 안 본다. **`=1` 을 쓰는 게 안전하다.**

## 매직 키워드 — 무엇이 자동으로 걸리나

`keyword-detector.mjs` 가 보는 목록. 슬래시로 부르지 않아도 이 말들이 스킬을 켠다.

| 스킬 | 트리거 |
|---|---|
| autopilot | `autopilot` · `full auto` · **"build/make me a app\|feature\|tool…"** · **"end to end"** · "handle it all" |
| ralph | `ralph` · `랄프` (랄프로렌은 제외) |
| ralplan · deep-interview · ultragoal | 그 이름 그대로 |
| ai-slop-cleaner | `deslop` · `anti-slop`, 또는 (clean·refactor·dedupe) + (slop·dead code·tech debt) |
| cancel | `cancelomc` · `stopomc` |
| 모드 안내만 삽입 | `ultrathink` · `deepsearch` · `tdd` · `code review` · `security review` · `deep-analyze` |

**`autopilot` 이 자연어 문장에도 걸린다는 게 중요하다** — "이 기능 만들어줘" 류가
전체 파이프라인을 켤 수 있다. 코드블록·URL·파일경로·인용부호 안은 제외되고,
"뭐야" "explain" 같은 정보성 문맥이면 버린다.

(`wiki` 는 매칭은 되는데 충돌 해소용 우선순위 배열에 빠져 있다 — OMC 쪽 결함으로 보인다.)

## MCP 도구 — 전제조건이 갖춰진 것만 쓸 수 있다

서버 이름이 `t` 라서 실제 도구명은 `mcp__plugin_oh-my-claudecode_t__<이름>` 이다.
코드에 정의된 것은 63개이고, `interop_*` 8개가 기본 비활성이라 **기본 등록은 55개**다.
(4.15.10 세션에서는 54개만 노출되고 `state_migrate_non_git` 이 빠져 있었는데,
5.0.2 로 재시작하니 55개가 다 나왔다 — 버전 차이였다.)

| 계열 | 개수 | 지금 쓸 수 있나 |
|---|---|---|
| `lsp_*` | 12 | **예** (재시작 후 확인). basedpyright + `OMC_PYTHON_LSP` — 아래 참고 |
| `ast_grep_*` | 2 | **예** (재시작 후 확인). 아래 참고 |
| `wiki_*` | 7 | 예. `.omc/wiki` 에 마크다운으로 저장 |
| `state_*` (+ `merge_readiness_*` 5) | 11 | 예. `.omc/state/` |
| `notepad_*` | 6 | 예. `.omc/notepad.md` |
| `project_memory_*` | 4 | 예. 단 `add_note`/`add_directive` 는 메모리가 이미 있어야 한다 |
| `shared_memory_*` | 5 | **아니오.** `~/.claude/.omc-config.json` 의 `agents.sharedMemory.enabled` 게이트, 현재 미설정 |
| `trace_*` · `session_search` | 3 | 예 |
| `skills_*` · `python_repl` · `deepinit_manifest` | 5 | 예 |
| `interop_*` (Codex 연동) | 8 | **아니오.** `OMC_INTEROP_TOOLS_ENABLED=1` 일 때만 등록 |

`.omc/` 는 이 저장소의 `.gitignore` 가 무시한다 — wiki·notepad·state 는 전부 그 아래라
**저장소에 안 남는다.** 세션 간에 남기려면 그걸 알고 써야 한다.

### 표를 믿지 말고 한 번 불러볼 것

`ast_grep_search` 를 실제로 호출해보고 위 표를 고쳤다. 모듈이 디스크에 있는 걸 확인했는데도
이렇게 실패했다.

```
@ast-grep/napi is not available.
Error: Cannot find package '@ast-grep/napi' imported from
       …/oh-my-claudecode/4.15.10/bridge/mcp-server.cjs
```

**MCP 서버는 플러그인을 업데이트해도 재시작 전까지 옛 버전으로 돈다.** 그리고 하필
`4.15.10/node_modules/` 에만 `@ast-grep/napi` 가 없다 (4.14.5 와 5.0.2 에는 있다).
재시작하면 5.0.2 브리지가 뜨면서 풀린다.

교훈은 그대로다 — **파일이 있다 ≠ 도구가 돈다.** 도구 가용성은 한 번 불러서 확인한다.

재시작 후 다시 불러 확인했다. 이번엔 돌았지만 결과가 `No matches` 였는데, 그건 패턴이
틀린 것이었다. **ast-grep 패턴은 완결된 AST 노드여야 한다.**

```
안 됨   def $NAME($$$ARGS)          ← 파이썬 함수는 본문이 있어야 노드가 된다
됨      def $NAME($$$ARGS):
            $$$BODY                  ← merge-settings.py 에서 6개 매치
```

"에러 없이 돌았다" 와 "제대로 물어봤다" 는 다르다. 빈 결과가 나오면 패턴부터 의심한다.

### lsp 를 켜려면 — basedpyright 를 골랐다

파이썬 서버는 `pyright` 가 아니다. `dist/tools/lsp/servers.js` 기준:

| | 명령 | 설치 | 2026-08-30 시점 |
|---|---|---|---|
| 기본 | `ty server` | github.com/astral-sh/ty | **0.0.75** — 릴리스 116번인데 아직 0.0.x |
| 선택 | `basedpyright-langserver --stdio` | `uv tool install basedpyright` | **1.39.10** (pyright 1.1.412 기반) |

`OMC_PYTHON_LSP=basedpyright` 일 때만 두 번째를 쓴다 — `resolvePythonServer()` 가
**정확히 그 문자열만** 인정한다. export 자리는 `shell/agents.sh`.

성숙한 쪽을 먼저 켠다. 처음 켜보는데 기능이 부실하면 "LSP 가 별로" 라는 틀린 결론에
도달하기 때문이다. 전환은 env var 한 줄이라 나중에 `ty` 와 비교하면 된다.
서버 설정은 22종이 정의돼 있다 (typescript · rust-analyzer · gopls · clangd · jdtls 등).

**검증**: `basedpyright-langserver --stdio` 에 `initialize` 를 직접 보내 응답을 받았다.
`definitionProvider` · `referencesProvider` · `hoverProvider` · `renameProvider` ·
`documentSymbolProvider` · `workspaceSymbolProvider` · `codeActionProvider` 7개를
전부 광고한다 — lsp_* 12개가 이 위에 얹힌다.
재시작 후 `lsp_servers` 가 basedpyright 를 **Installed** 로 잡는 것도 확인했다
(나머지 19종은 Not Installed 로 설치 힌트와 함께 나온다).

### 그래서 grep 과 뭐가 다른가

`merge-settings.py` 의 `merge` 함수를 찾아보면 차이가 그대로 보인다.

```
grep -n "merge"            10줄   ← 파일명 언급(docstring 3줄) · merged 변수 · 파라미터까지
lsp_find_references         3곳   ← 18:5 선언 · 25:26 재귀 호출 · 46:14 render 안의 호출
```

**grep 은 글자를 찾고 LSP 는 의미를 안다.** "이 함수 시그니처를 바꾸면 어디가 깨지나" 를
물을 때 이 차이가 결과를 가른다. 대체가 아니라 보완이다 — 넓게 훑는 건 여전히 grep 이 빠르다.

**주의 — 기본 엄격도가 매우 높다.** `scripts/merge-settings.py`(130줄)에 경고 **102개**가
붙는데 거의 전부 `reportUnknown*` · `reportAny`, 즉 "타입 주석이 없다" 는 말이다.
에러는 0개다. `--level error` 로 보면 `0 errors, 0 warnings`.

```
31 reportUnknownVariableType · 28 reportUnknownArgumentType · 12 reportUnknownParameterType
11 reportUnknownMemberType   · 11 reportMissingParameterType · 8 reportAny
```

주석 없는 파이썬에 `lsp_diagnostics` 를 그냥 쓰면 이 벽을 받는다. 프로젝트별로
`pyproject.toml` 의 `typeCheckingMode` 를 낮추는 게 맞다 — 전역 설정으로 풀 문제가 아니다.

## 실제 사용량 (2026-08-30 실측)

세션 873개 · 프롬프트 2825개 기준. 슬래시 477회 중 OMC 는 73회.

```
autopilot 31 · deep-interview 9 · ultragoal 8 · ralph 5 · deepinit 4
ralplan 4 · ultrawork 4 · omc-setup 3 · autoresearch 2 · deep-dive 2 · team 1
```

| 자동 경로 | 실측 |
|---|---|
| 모델이 OMC 스킬을 알아서 고른 횟수 | **3회** |
| 매직 키워드 훅이 걸린 횟수 | **2회** |
| MCP 도구 총 호출 | **4회** (python_repl 2 · session_search 1 · project_memory_add_note 1) |
| 에이전트 19개 중 실제 호출된 것 | **7개** (executor 56 · code-reviewer 12 · document-specialist 5 · 나머지 2회 이하) |

**훅 25개와 MCP 55개가 매 프롬프트·매 도구호출마다 도는데, 거기서 나오는 결과는 거의 안 쓴다.**
실제로 쓰는 것은 슬래시 명령 11개와 에이전트 7개다.

안 불리는 이유의 일부는 확인된다 — 안 쓰는 에이전트 12개의 `description` 이
**전부 "무엇인지" 로 시작하고 "언제 쓰는지" 로 시작하는 것이 하나도 없다.**
`docs/skills.md` 에서 낸 결론이 OMC 자신의 카탈로그에 그대로 적용된다. 남의 플러그인이라
고칠 수 없으므로 대응은 **이름을 직접 지정하는 것** 뿐이다 (`docs/orchestration.md`).

## 이 문서가 생긴 이유 (2026-08-30)

4.15.10 을 두 달 넘게 쓰다 5.0.2 로 올리면서, 무엇이 깔려 있고 무엇이 실제로 도는지를
처음 세어봤다. 업데이트 자체보다 **"쓰는 것 11개 / 도는 것 80개" 라는 비율**이 알게 된 것이다.
