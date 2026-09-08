# Codex 설정 조사와 배선안

조사일: 2026-09-07. 아래는 변경 전 조사 시점의 기록이다. 이후 구현된 항목과
2026-09-08 새 세션 HUD 미표시 문제는 [변경 기록](codex-changes.md)을 정본으로 본다.
본문의 '현재'와 '미적용'은 조사 당시를 가리키며 최신 적용 상태가 아니다.

## 결론

관측된 `codex_apps` 시작 실패는 HTTP 401 `token_expired`다. OMO의 Context7·grep.app·CodeGraph·LSP 연결 실패와 구분해야 한다. agentic-memory의 Codex 연결 누락과 HUD 표시 차이는 별도의 설정 문제다.

현재 자산을 보존하는 권장 구성은 Codex가 인증/Apps/내장 상태줄을, OMX가 기본 작업 실행을, OMO가 선택한 개발 도구를, agentic-memory가 호스트 공용 메모리를 맡는 것이다. OMX와 OMO의 자동 작업 계속 실행 기능은 같은 작업에서 중복으로 작동시키지 않는다. 이것은 조사에 따른 권고이며 현재 충돌이 인증 오류를 일으켰다는 뜻은 아니다.

## 직접 확인한 로컬 상태

| 항목 | 관측 | 해석과 한계 |
| --- | --- | --- |
| Codex | `codex-cli 0.153.4`, `codex login status`는 ChatGPT 로그인 | 로그인 캐시가 있다는 것과 Apps 초기화 성공은 별도다 |
| 인증 캐시 | 9월 7일 19:22 KST 갱신, 조사 시 access token 미만료, refresh token 존재 | 토큰 값이나 계정 식별자는 출력·기록하지 않았다. 실패 순간 토큰은 확보하지 않았다 |
| OMX | 0.18.11, npm 조회 최신 0.21.3 | 업데이트 검토 대상. 버전 차이만으로 401 원인을 판단하지 않는다 |
| OMO | 4.19.4, 조사한 upstream 패키지도 4.19.4 | 설치 manifest가 선언한 훅 21개와 MCP 실행 파일 존재. git-bash 관련 훅 2개는 파일/trust 항목이 남아 있어도 manifest 선언에서는 제외되어 있다 |
| 일반 MCP | Context7·grep.app·CodeGraph 실제 도구 호출 성공, LSP initialize 성공 | `codex_apps` 성공을 입증하는 검사가 아니다 |
| Codex 실행 | 이전 턴의 새 `codex exec --ephemeral`가 `OK`로 종료 | 모델 및 기본 훅 실행 증거이며 Apps 전용 검사는 아니다 |
| dotfiles | `./install.sh --check`: 18개 정상 | 메모리 및 Apps 연결을 검사하지 않는다 |
| OMX 진단 | 16개 통과, Explore 실행 파일 관련 경고 1개 | 토큰 만료와 별개다 |
| agentic-memory | Claude 훅 5개, Codex 훅/MCP 등록 없음 | Codex에서 자동 회수·캡처·보존·증류 연결이 누락됐다 |
| 메모리 데몬 | 기본 주소 `127.0.0.1:8765/health` 연결 거부 | 이 시점 기본 포트에 리스너가 없다. 유휴 종료가 정상인 설계라 설치 손상 증거는 아니다 |
| 상태줄 | Codex 내장 항목 6개, 조사한 tmux pane에서 추가 HUD 없음 | 별도 HUD 패널이 해당 세션에 연결됐다는 증거가 없다 |
| 런타임 | PID 1은 systemd, 사용자 systemd 상태 `running` | 공용 데몬을 user service로 관리할 수 있는 기반이 있다 |

로컬 근거:

- `~/.codex/config.toml`: `[tui]`, OMO 플러그인 설정, OMX Stop 훅의 `enabled = false`.
- `~/.codex/hooks.json`: OMX 훅 및 `agent-window-label`; agmem 없음.
- 비공개 머신별 `settings-overlay.json`: Claude에만 `AGMEM_CONFIG`, `AGMEM_DAEMON_LOG` 및 agmem 훅 등록.
- `shell/agents.sh:235`: `codex()`는 `AGENT_PROFILE`을 설정하고 `command codex` 실행. OMX HUD 실행기는 호출하지 않는다.
- `install.sh:244`: Codex 검사는 hooks.json 최상위 키와 `agent-window-label` 문자열 존재만 확인.

## codex_apps 인증 오류의 범위

사용자가 제공한 로그는 MCP `initialize` 요청을 서버가 HTTP 401 `token_expired`로 거부한 증거다. 실행 파일 누락, stdio 프로토콜 손상, OMO 훅 문제라는 증거는 아니다. Codex의 Apps 연결은 ChatGPT 인증 경로를 사용하므로 일반적인 사용자 등록 MCP의 OAuth 로그인과 구분한다. `codex mcp login codex_apps`를 일반적인 복구 명령으로 제시하지 않는다.

공식 문서는 Codex가 인증 캐시를 공유하고 access token을 자동 갱신한다고 설명한다. 그러나 현재 캐시가 미만료라는 사실만으로 실패 당시 요청에 어떤 토큰이 사용되었는지 알 수 없다. 오래 실행된 프로세스의 인증 상태, 갱신 시점, 서버 측 토큰 판정 중 어느 것이 원인인지는 아직 확정하지 않았다. 근거: [공식 인증 문서](https://learn.chatgpt.com/docs/auth).

비슷하게 새 토큰과 정상 모델 응답이 있어도 Apps에서 401이 발생한다는 [upstream 보고 #38679](https://github.com/openai/codex/issues/38679)가 있다. 이는 동일 원인이라는 증거도, 현재 설치 버전에서 해결됐다는 증거도 아니다. 따라서 재설치나 일괄 로그아웃을 첫 조치로 삼지 않는다.

복구 순서는 다음과 같다.

1. 현재 갱신된 인증을 읽는 새 Codex 프로세스에서 Apps initialize를 별도로 확인한다. 기존 모델 호출 성공은 대체 검사가 아니다.
2. 실패가 반복되면 시각, 버전, 인증 저장 방식, 갱신 전후 여부를 비밀값 없이 기록한다. 이 조사에서는 토큰 강제 주입 환경변수가 설정되지 않았음을 확인했다.
3. 인증 갱신이 실제로 실패한 경우 정상 ChatGPT 로그인 흐름으로 자격 증명을 갱신한다. 로그아웃은 공유 인증을 쓰는 다른 세션에도 영향을 주므로 무조건 실행하지 않는다.
4. 새 로그인 뒤에도 Apps만 실패하면 로컬 harness 재설치보다 Apps 인증 경로의 회귀/서버 문제를 우선 조사한다. Apps 비활성화는 기능을 포기하는 우회책이지 인증 복구가 아니다.

현재 Apps가 복구됐다고 판정할 직접 initialize 증거는 없다.

## Harness별 설정 경계와 선택

`opencodex`는 대상 프로젝트가 명확하지 않아 OpenAI Codex와 OpenCode를 모두 비교했다. 별도의 동명 프로젝트를 확인했다고 주장하지 않는다.

| 구성 | 설정 방식 | 우리 환경에서 맡길 역할 |
| --- | --- | --- |
| OpenAI Codex | 사용자/프로젝트 TOML, native hooks, plugins, ChatGPT 인증 | 실행 호스트, Apps 인증, 기본 상태줄 |
| oh-my-codex / OMX | `omx setup`으로 AGENTS·skills·roles·설정 설치, OMX 런타임과 HUD | 기존 AGENTS 계약과 작업 조율을 유지하는 기준 |
| LazyCodex / OMO | Codex plugin manifest, hooks, MCP, skills 및 설정 로더 | 필요한 개발 도구를 유지하되 OMX와 작업 루프 소유권 조정 |
| OpenCode | 별도 `opencode.json`, `.opencode`, plugins와 `tui.json`, 별도 인증 상태 | Codex 위에 얹는 계층이 아니라 대체/병행 호스트 |
| Claude Code / OMC | Claude settings와 hooks, 명령 기반 statusline | 기존 사용자 환경 보존; 공용 메모리 서비스만 공유 |

근거: [Codex 설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference), [OMX 설치·구조](https://github.com/Yeachan-Heo/oh-my-codex/blob/304fb3b4825c4132c273732b14d2d5e86b54f8e3/README.md), [OMO manifest](https://github.com/code-yeongyu/lazycodex/blob/10f95587d3aeacf208cc1fee88a91315962d31e8/plugins/omo/.codex-plugin/plugin.json), [OpenCode 설정](https://opencode.ai/docs/config/), [OpenCode plugins](https://opencode.ai/docs/plugins/).

추천은 새 harness를 추가 설치하는 것이 아니라 현재 Codex를 호스트로 유지하면서 설정의 소유자를 분리하는 것이다. OMX 중심은 현재 AGENTS 자산을 보존하려는 선택이지 유일한 정답은 아니다. OMO 중심을 택할 수도 있지만 그때는 OMX의 자동 실행 규칙과 생성 역할을 함께 정리해야 한다. 양쪽 기본값을 모두 활성화하는 방식은 권하지 않는다. OMO의 tools-only 구성이 공식 단일 프리셋이라고 확인된 것은 아니므로 개별 비활성화 지원 범위를 구현 전에 확인한다.

OpenCode를 병행하더라도 공유할 것은 agentic-memory의 서비스/API와 프로젝트 정책이며, Codex 인증 파일이나 훅 JSON 전체를 복사할 대상은 아니다.

## HUD의 세 가지 소유자

| 화면 | 데이터와 렌더러 | 현재 환경에서의 의미 |
| --- | --- | --- |
| Claude 상태줄 | Claude가 전달한 JSON → `agent/statusline` → OMC HUD 및 캐시·비용 줄 | 기존 커스터마이징을 그대로 보존할 대상 |
| Codex 하단 상태줄 | Codex의 `[tui].status_line` 내장 항목 | 토큰·한도·비용·브랜치 등 기본 세션 지표 표시 |
| OMX 추가 HUD | `omx hud`, `.omx` 실행 상태 | 작업 모드·팀·진행 상태를 별도 tmux pane 등에 표시 |

OMO 플러그인을 켰다는 사실만으로 Claude OMC HUD가 Codex에 생기지는 않는다. 현재 `omx hud --json`은 동작하지만 활성 모드는 없고 토큰 필드는 0이다. 이 0을 실제 세션 사용량으로 표시하면 안 된다. 네이티브 세션 지표는 Codex 상태줄을 정본으로 사용한다.

공식 설정의 `tui.status_line`은 항목 이름 배열이다. Claude의 임의 명령 출력 방식과 다르므로 `agent/statusline`을 그대로 꽂는 설정이 아니다. 근거: [Codex 설정 참조](https://learn.chatgpt.com/docs/config-file/config-reference), 로컬 `agent/statusline`, 설치된 `~/.codex/skills/hud/SKILL.md`.

## agentic-memory: 재사용 가능한 부분과 검증할 부분

### 재사용 가능한 부분

agentic-memory는 이미 `rollout-*.jsonl`을 Codex 세션으로 판별하고 `session_meta`, `response_item`, 사용자/assistant 메시지, 도구 호출과 결과를 해석한다. 새 Codex 대화 파서를 만드는 것이 우선 작업은 아니다.

근거: 별도 agentic-memory 저장소의 `src/agmem/sessions/__init__.py:412`, `tests/test_sessions.py:136`. 기존 테스트의 존재를 확인했으며 이 초기 조사 시점에는 실행하지 않았다.

| Codex 이벤트 | 연결할 기존 모듈 | 목적 |
| --- | --- | --- |
| SessionStart | `agmem.hooks.recall` | 프로젝트의 기존 기억 회수 |
| UserPromptSubmit | `agmem.hooks.recall_prompt` | 질의에 맞는 기억 주입 |
| UserPromptSubmit | `agmem.hooks.capture` | 사용자 턴 비동기 저장 |
| PreCompact | `agmem.hooks.preserve` | 압축 전 원문 보존 |
| SessionEnd | `agmem.hooks.distill` | 종료된 세션의 경험 증류 요청 |

현재 조사한 Codex 소스에는 `prompt`, `session_id`, `cwd`, `transcript_path`가 있으며, `SessionStart`의 `source="compact"`도 존재한다. agmem이 기대하는 필드와 맞는다. 단, 아래 시간 제한과 실패 처리를 검증해야 실제 호환성을 주장할 수 있다.

### 호환성 경계

1. **종료 시간 제한:** 조사한 Codex 소스는 SessionEnd를 동기로 처리하며 timeout을 최대 3초로 제한한다. agmem HTTP 요청 제한은 5초다. 정상적으로 빠른 응답만 테스트하면 이 불일치를 놓친다. 종료 훅은 로컬 큐 기록 또는 짧은 요청으로 끝나고 증류는 데몬에서 수행해야 한다.
2. **전송 실패 후 보존:** `distill`과 `preserve`는 첫 health 검사부터 실패하면 spool한다. health 성공 뒤 POST가 실패하면 예외를 기록하고 종료하며 그 경로에서는 spool하지 않는다. 이 정적 코드 경로는 확인됐지만 이번 조사에서 장애 주입으로 재현하지 않았다.
3. **호스트 표시:** capture는 `source`가 없으면 `AGMEM_HOOK_SOURCE`, 그마저 없으면 `claude-code`를 사용한다. Codex 훅에는 `AGMEM_HOOK_SOURCE=codex`가 필요하다.
4. **저장소 일치:** Claude에 설정된 `AGMEM_CONFIG`가 Codex에는 없다. `AGMEM_CONFIG`, `AGMEM_DATA_DIR`, `AGMEM_NAMESPACE`, `AGMEM_DAEMON_URL`을 공용 서비스와 클라이언트에 일치시켜야 한다. 현재 HTTP 훅은 namespace를 보내지 않아 서버 시작 시 기본 namespace가 적용된다. 클라이언트 환경변수만 바꾸어 요청별 격리가 된다고 가정하면 안 된다.
5. **기동 순서:** 훅이 데몬을 띄우는 방식과 고정 HTTP MCP 주소를 함께 쓰면 MCP initialize가 데몬 준비보다 먼저 실행될 수 있다. 서버 등록만으로 서비스 준비가 보장되지 않는다.
6. **보존과 증류의 차이:** 현재 `/hooks/preserve`는 저장 완료까지 기다린다. `/hooks/distill`은 백그라운드 스레드를 시작하고 `queued`를 반환한다. 일부 설명 문서의 두 경로 모두 즉시 반환한다는 서술보다 실제 코드를 기준으로 잡는다.

근거: agmem `hooks/capture.py:88`, `hooks/daemon.py:40`, `hooks/preserve.py:45`, `hooks/distill.py:37`, `mcp/server.py:508`; Codex `hooks/src/engine/discovery.rs:525`, `:740`, `hooks/src/events/user_prompt_submit.rs:84`.

Codex 최신 소스 기준점은 `4875084025582f9443afeb907e2aa20644241dda`다. SessionEnd 동기 실행과 최대 3초 제한은 설치 버전 `rust-v0.153.4`의 실제 commit `3d2ee51ca2d5db578f328aa75e20aa22c0197c9a`에서도 [discovery 구현 및 테스트](https://github.com/openai/codex/blob/3d2ee51ca2d5db578f328aa75e20aa22c0197c9a/codex-rs/hooks/src/engine/discovery.rs)를 확인했다. 나머지 최신 소스 관찰은 설치 바이너리의 실제 훅 실행 검증을 대신하지 않는다.

## 권장 배선

```text
Claude Code ─ Claude 훅 ─┐
                       ├─ 공용 agentic-memory HTTP 데몬 ─ 기존 저장소
Codex ─ Codex 훅 ───────┘                  │
      └ MCP agentic_memory ───────────────┘

Codex ─ ChatGPT 인증 ─ codex_apps ─ 연결된 Apps
      ├ OMO ─ Context7 / grep.app / CodeGraph / LSP
      ├ OMX ─ 선택한 작업 실행 / 팀 / 작업 상태
      └ 내장 상태줄 + 기존 tmux 창 이름 + 필요 시 OMX HUD
```

### 공용 메모리 데몬

이 머신에서는 user systemd 서비스 한 개가 HTTP 데몬을 소유하는 구성을 우선 권장한다. 서버의 기존 CLI를 사용하고 `--transport http --host 127.0.0.1 --port 8765 --organizers experience --idle-timeout 0`으로 기존 훅의 경험 증류 동작을 보존한다. CLI 기본 organizer는 다르므로 `experience`를 생략하면 안 된다.

서비스는 현재 Claude가 사용하는 `AGMEM_CONFIG` 파일을 참조한다. 비밀값을 unit이나 dotfiles에 복사하지 않는다. 클라이언트의 자체 데몬 생성은 서비스 전환 후 `AGMEM_NO_DAEMON=1`로 일관되게 끄고, 서비스 준비 후 클라이언트가 연결하도록 한다. 이 변경은 Claude에도 영향을 주므로 실제 전환 시 양쪽을 함께 검증해야 한다.

상주 메모리 사용이 부담되면 기존 유휴 종료 방식을 유지할 수 있다. 그 경우 MCP 연결 전에 데몬 준비를 기다리는 실행 경로가 추가로 필요하다. 단순히 startup timeout만 늘리는 것으로 연결 거부와 기동 순서가 해결된다고 보장할 수는 없다.

Codex MCP 설정의 목표 형태는 다음과 같다. 서비스가 준비된 뒤 적용할 예시이며 현재 설치한 설정이 아니다.

```toml
[mcp_servers.agentic_memory]
url = "http://127.0.0.1:8765/mcp"
startup_timeout_sec = 30
tool_timeout_sec = 60
required = false
```

시간값은 초기 제안이다. 실제 initialize와 일반 조회의 측정값으로 조정한다. 훅 환경은 Codex 도구용 셸 설정에만 의존하지 말고 훅 실행 명령 또는 공용 래퍼가 명시적으로 공급하게 한다.

### 실행 규칙과 업데이트 소유권

- `AGENTS.md`, 역할별 agent, 기본 작업 루프는 OMX를 기준으로 유지한다.
- OMO 도구는 유지하되 자동 계속 실행·강제 워크플로 규칙은 OMX와 중복되지 않게 선택한다. 설치된 OMO에 개별 설정으로 지원되는지 확인한 뒤 적용한다.
- 버전별 플러그인 캐시를 개인 설정의 정본으로 편집하지 않는다. 현재 git-bash 관련 manifest 차이를 그대로 덮어쓸지 여부도 업데이트 전에 확인한다.
- `auth.json`, OAuth 상태, 훅 trust hash는 머신 로컬이다. dotfiles에는 원하는 설정과 생성 절차를 둔다.
- `omx setup` 및 OMO 업데이트 이후 원하는 설정이 유지되는지 검사한다. 두 설치기를 반복 실행하는 것만으로 정책이 정리되지는 않는다.

### dotfiles의 책임

현 `codex/config.template.toml`은 이식용 자료이며 자동 동기화 정본으로 동작하지 않는다. Codex 설정도 Claude처럼 공용 선호와 머신별 경로를 분리하고, 기존 TOML/훅 구조를 보존하는 병합 단계를 두는 것이 적절하다.

구현 시 검토할 범위는 `codex/config.template.toml`, `codex/hooks.snippet.json`, 머신별 Codex overlay, `install.sh`의 Codex 검사/병합, 선택적인 공용 메모리 서비스 정의다. 훅은 기존 이벤트 배열 끝에 추가해 기존 인덱스 기반 trust를 불필요하게 바꾸지 않는다. 실제 적용 후 정상적인 trust 절차로 검증한다.

`install.sh --check`가 증명할 범위도 늘려야 한다. 설정 파일 존재, 예상 훅과 환경, 실행 파일 존재, 서비스 health, MCP initialize, 선택한 자동 실행 규칙, 상태줄 설정을 각각 구분한다. 인증·네트워크 검사는 오프라인 정적 검사와 결과를 분리해 보고한다.

## 적용 완료의 판정 기준

1. 새 Codex 시작에서 `codex_apps` initialize가 성공한다. 일반 모델 응답이나 다른 MCP 성공으로 대체하지 않는다.
2. 비밀값 없이 Apps 인증 실패와 일반 MCP 실행 파일/연결 실패를 구별할 수 있다.
3. 격리된 시험 namespace에서 Claude와 Codex의 캡처 → 회수 → 압축 보존 → 종료 증류 흐름을 확인한다. namespace를 HTTP로 명시하거나 별도 시험 데몬을 써서 실제 기억에 시험 데이터를 섞지 않는다.
4. 메모리 서버가 내려간 경우와 health 직후 POST가 실패하는 경우를 검증한다. 대화는 계속되고 보존할 데이터는 재처리 가능해야 한다.
5. Codex 종료 훅은 설치 버전의 시간 제한 안에 끝난다. 강제 종료까지 SessionEnd를 보장한다고 주장하지 않는다.
6. 압축 후 동일 세션의 기억 회수와 다른 프로젝트 기억의 섞임 방지를 확인한다.
7. 상태줄은 80칸·120칸에서 확인하고, 추가 HUD를 쓴다면 세션별 데이터와 pane 정리까지 검증한다.
8. 설정 병합을 두 번 수행해도 중복 훅이 생기지 않고, 기존 Claude 설정과 사용자 편집이 보존된다.

이 문서는 위 검사를 수행한 구현 완료 보고서가 아니다. 실제 세션 데이터의 수집·재증류, 인증 재로그인, 설치 업데이트, 서비스 전환은 이번 조사에서 수행하지 않았다.
