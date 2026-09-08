# Codex 배선과 HUD 변경 기록

기록일: 2026-09-08. 이 문서는 구현·검증·미해결 사항을 구분한다.

## 커밋

- `4d4f7a8`: 같은 상태에서도 tmux 탭 기호와 색을 복구한다.
- `ee7e2e2`: Codex 공용 메모리·설정 병합·고정 HUD와 직접 테스트를 연결한다.
- 문서 커밋: 변경 전 조사, 복원 절차, 검증 한계와 새 세션 미표시 보고를 함께 남긴다.

배포 전 직접 실행기 `agent/codex-hud.py`의 실행 비트도 보완하고 심링크 경유 `--help`를
확인했다. 이는 CLI 배포 권한 보완이지 새 세션 HUD 문제의 원인 규명이나 수정이 아니다.

## 구현한 것

| 범위 | 파일 | 변경 이유 |
| --- | --- | --- |
| tmux 탭 상태 복구 | `agent/window-label.sh`, `scripts/test-window-label.py` | 상태가 같아도 사라진 기호·색 필드를 복구 |
| Codex 설정 병합 | `scripts/codex-wiring.py`, `scripts/codex_wiring_{hooks,toml}.py`, `codex/hooks.snippet.json`, `codex/config.template.toml` | 기존 설정과 훅 순서를 보존하면서 메모리·상태줄·워크플로 소유권 배선; 변경 전 비공개 백업 |
| 공용 메모리 | `agent/memory-hook`, `agent/memory-daemon`, `agent/agentic-memory.service` | 기존 agentic-memory 설치를 사용하고 localhost user service로 공유; 실제 기억·인증은 저장소 밖에 유지 |
| Apps 진단 | `scripts/check-codex-apps.mjs` | 일반 모델 응답과 구분해 app-server MCP 상태를 검사 |
| HUD 데이터 | `agent/codex_hud_{data,sqlite,types}.py` | pane에 연결된 정확한 세션만 조회; 현재 컨텍스트와 누적 토큰을 구분 |
| HUD 표시·수명 관리 | `agent/codex-hud.py`, `agent/codex_hud_render.py`, `agent/codex-hud-launcher`, `shell/agents.sh`, `tmux/tmux.conf` | 분할 pane 대신 탭 위 고정줄과 상세 팝업; 원래 탭 보존 및 소유권이 확인된 이전 HUD만 정리 |
| 설치 | `install.sh` | 실행기·서비스 심링크와 정적 배선 검사; live TOML 변경은 별도 명시적 명령 |

내장 상태줄은 컨텍스트·5시간/주간 한도·토큰·추정 비용·브랜치 순이다.
추가 고정줄은 컨텍스트·한도·관측 나이를 우선하고 폭에 따라 토큰·캐시·모델 등을 표시한다.
팝업은 현재 **Alt+a → h**, 닫기는 **q**, 스크롤은 방향키/PageUp/PageDown이다.

메모리 `ready`는 health 응답만 뜻한다. recall/save 성공은 관측하지 못하면 표시하지 않는다.
에이전트는 최대 8개의 최근 자식 관계이며 실행 중 개수가 아니다. 작업 수는 신뢰할
세션별 원천이 없어 unavailable이다. MCP 전체 정상 여부도 HUD에서 추정하지 않는다.

## 확인한 범위

- HUD Python 회귀 22개: 수집 10, 렌더 10, OMX 세션/cwd 일치 2.
- 설정 병합 8개와 워크플로 소유권 6개; Claude statusline/cacheline 4+8개와 창 라벨 8개.
- 격리 tmux의 등록·중복 호출·해제·다른 창 이동·탭 보존·소유권 검사, mock 실행기의 셸 진입 경로.
- 실제 기존 세션의 고정줄 표시. PTY → xterm.js 화면 17개를 두 독립 검토자가 확인:
  60/80/120칸, 한글, 데이터 없음, 크기 변경, 팝업 스크롤·닫기, 다른 창 이동·복귀.
- 변경 Python 대상 Ruff·basedpyright 검사와 셸 문법 검사. 저장소 전체 typing 통과를 뜻하지 않는다.
- 당시 live memory health 정상, Apps 별도 프로브 성공. 과거 성공이 이후 인증 만료나 연결 상태를 보장하지 않는다.

스크린샷·대화·세션 ID·머신별 경로가 포함될 수 있는 `.omo/` 실행 증거와 비공개 `local/`
수정은 push 대상에서 제외한다. 실제 기억에 합성 시험 데이터를 쓰지 않는다.

## 미해결: 새 세션에서 HUD가 나타나지 않음

2026-09-08 사용자가 기존 세션에서만 보이고 새 세션에서는 아예 안 보인다고 보고했다.
**미해결이며 이번 push에 수정 완료로 포함하지 않는다.** 이전 완료 보고는 실제 진입 경로
전체를 검증하지 못했다. 격리 lifecycle 테스트의 성공으로 이 사용자 보고를 대체하지 않는다.

구조상 추가 HUD는 tmux와 pane 등록에 의존한다. 셸 래퍼를 우회하는 실행,
이전 셸 함수, 시작 훅의 실행·신뢰 상태, 다른 설정 홈 등이 확인 후보이지만 확정 원인은 아니다.
후속 작업에서는 사용자가 실제로 사용하는 새 터미널/새 창/`codex`/`resume`/harness 진입을
구분해 재현하고, 첫 입력 전·첫 입력 후·종료·재진입을 각각 확인해야 한다.

## 추천만 한 것: 미적용

- 핵심 사용량은 Codex 내장 상태줄, 추가 활동·메모리 정보는 얇은 보조줄에 상시 표시.
- 상세 팝업은 ID·경로 등 드물게 보는 정보 위주로 축소.
- prefix 없이 F8 한 번으로 팝업 열기: 기존 키/터미널 충돌 확인이 선행되어야 한다.
- 새 세션 자동 적용 문제를 먼저 해결한 뒤 레이아웃·키를 변경.

사용자가 추천만 요청했으므로 위 제안에 대한 코드·설정 변경은 하지 않았다.

## 반복 가능한 로컬 검사

시험에는 Python 3.12+ (`typing.override` 사용), Node.js, Bash, tmux와 `script`가 필요하다.
메모리 훅 시험은 mock Python을 사용한다.

```bash
python3 scripts/test-codex-hud.py
python3 scripts/test_codex_hud_data.py
python3 scripts/test_codex_hud_omx_scope.py
python3 scripts/test-codex-wiring.py
python3 scripts/test-codex-wiring-workflow.py
python3 scripts/test-window-label.py
python3 scripts/test-statusline.py
python3 scripts/test-hud-cacheline.py
bash scripts/test-codex-fixed-hud.sh
bash scripts/test-codex-hud-lifecycle.sh
bash scripts/test-codex-launch.sh
bash scripts/test-memory-hook.sh
```

복원·백업·서비스 전환 절차는 [설정 안내](codex-setup.md), 변경 전 조사 근거는
[배선 조사](codex-wiring-audit.md)를 참고한다. `install.sh --check`는 전체 런타임 검증이 아니다.
