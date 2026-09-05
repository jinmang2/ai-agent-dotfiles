# 스테이터스라인 (OMC HUD)

프롬프트 밑에 뜨는 막대다. 사용량·모델·컨텍스트·돌고 있는 에이전트를 보여준다.
OMC 가 만들지만 **설정은 `claude/settings.json` 의 `omcHud` 키에 두므로 이
저장소가 소유한다.** 넣는 순간 모든 머신에 그대로 간다.

지금 값 (2026-09-05, OMC 4.14.5 ~ 5.1.0 에서 동일):

```jsonc
"omcHud": {
  "preset": "focused",
  "elements": {
    "useBars": false,        // 기본 프리셋 focused 가 막대를 켠다 (4.14.5 이래) — 좁은 창에서 자리만 먹는다
    "contextBar": false,     // transcript 기반 ctx 가 0% 로 굳어 있었다. Claude Code 자체 표시가 있다
    "promptTime": false, "sessionHealth": false, "thinking": false,
    "activeSkills": false, "lastSkill": false,
    "maxOutputLines": 6      // 기본 4 는 좁은 창에서 `... (+3 lines)` 로 잘렸다
  }
}
```

남긴 것: 브랜치 줄 · 모델 · 5h/주간/모델별 한도 · 호출 수 · 돌고 있는 에이전트(최대 3줄).

**좁은 창에서 줄이 갈리는 이유.** `maxWidth` 를 안 주면 OMC 가 터미널 폭을 재고
`wrapMode` 를 `truncate` 에서 `wrap` 으로 **스스로 바꾼다** (`dist/hud/index.js`). 그래서
메인 줄이 ` | ` 경계마다 갈라져 여러 줄이 되고, 그 다음 `maxOutputLines` 가 뒤를 자른다.
`wrapMode: "truncate"` 를 명시해도 같은 코드가 다시 `wrap` 으로 바꾸므로 소용없다.
줄 수를 줄이는 방법은 요소를 빼는 것뿐이다.

## 어떻게 그려지나

Claude Code 의 `statusLine` 설정은 계약이 아주 단순하다. 렌더할 때마다 명령을
실행하고 stdin 으로 세션 JSON(`session_id` `transcript_path` `cwd` `model`
`version`)을 밀어넣은 뒤, **stdout 을 그대로 막대로 그린다.** 그게 전부다.
명령이 없거나 실패해서 stdout 이 비면 경고 없이 빈 줄이 된다.

우리 `settings.json` 의 명령은 이것이다:

```
sh ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hud/omc-hud-cache.sh \
   ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hud/omc-hud.mjs
```

- `omc-hud.mjs` — 얇은 로더. OMC dist 를 플러그인 루트 → 플러그인 캐시 →
  마켓플레이스 클론 → npm 전역 순으로 찾아 렌더를 호출한다.
- `omc-hud-cache.sh` — 그 앞의 캐시 래퍼. Node 콜드 스타트가 수백 ms 인데
  렌더는 타이핑마다 일어나므로, 세션별 마지막 줄을 `hud/cache/` 에 두고 즉시
  `cat` 한 뒤 갱신은 백그라운드로 돌린다. 세션의 첫 프레임만 동기로 그린다
  (Claude Code 는 사용자 입력이 있기 전엔 statusLine 을 다시 묻지 않으므로,
  비동기로 하면 `[OMC] Starting...` 에 멈춰 있게 된다).

이 스크립트들은 저장소에 없다. `install.sh` 가 OMC 마켓플레이스 클론에서
5개 파일을 복사해온다. 자세한 건 README 의 "새 머신 복원" 을 보라.

데이터 출처는 각각 이렇다. 사용량 API → `5h:` `wk:`, transcript jsonl →
`ctx:` `T:`, `.omc/` 상태 파일 → ralph·autopilot·에이전트 줄,
`basename($CLAUDE_CONFIG_DIR)` → `profile:`.

## profile 표시는 tmux 마커와 다른 변수를 본다

헷갈리기 쉬운 지점이라 적어둔다.

| | 보는 변수 | 표 |
|---|---|---|
| tmux 창 번호색 (파랑/보라) | `AGENT_PROFILE` | `agent/profiles.conf` |
| HUD 의 `profile:` | `CLAUDE_CONFIG_DIR` 의 basename | 없음 (문자열 그대로) |

HUD 는 `AGENT_PROFILE` 을 아예 모른다. `CLAUDE_CONFIG_DIR` 이 비어 있으면
`profile:` 줄을 통째로 생략한다. 그래서 `shell/agents.sh` 는 personal 계정도
`claude()` 함수로 감싸 두 변수를 다 채운다 — 안 그러면 창 번호색으로는 계정이
구분되는데 HUD 로는 어느 계정인지 알 수 없다.

## 계정을 여러 개 쓸 때 — 사용량 캐시

OMC 는 자격증명을 `<config-dir>/.credentials.json` 에서 계정별로 읽지만, 5시간·주간
한도의 응답 캐시도 `<config-dir>/plugins/oh-my-claudecode/.usage-cache-*.json` 에
둔다. 그래서 계정 간에 `plugins/` 를 통째로 심링크하면 **두 계정이 캐시 파일 하나를
나눠 쓰게 되어, 마지막으로 렌더한 계정의 숫자가 양쪽에 다 뜬다.** 성공 캐시 TTL 은
90초지만, 그게 지나도 최대 15분(`MAX_STALE_DATA_MS`)까지 옛 값을 먼저 내주고 뒤에서
갱신하므로 틀린 숫자가 한참 굳어 있는다.

`shell/agents.sh` 의 `CLAUDE_ACCOUNT_LOCAL` 이 이 경로를 계정별로 가른다. README 의
"다중 계정" 을 보라.

## 설정하는 곳

`claude/settings.json` 최상위에 `omcHud` 키를 둔다. 대화형으로 고르려면
`/oh-my-claudecode:hud` 를 쓰되, 결과가 `settings.json` 에 떨어지므로 그
diff 를 확인하고 커밋해야 한다.

```jsonc
"omcHud": {
  "preset": "focused",
  "elements": { "hostname": true },
  "thresholds": { "contextWarning": 70 }
}
```

`preset` 이 on/off 의 바탕을 깔고, `elements` 가 그 위에 개별 덮어쓰기를 한다.

## 프리셋

`minimal` · `focused` (기본) · `full` · `opencode` · `dense`.

## elements — 전체 목록

기본값은 OMC 4.14.5 기준이며 5.0.2 에서도 키가 동일하다 (신규·삭제 없음).

### 표시 여부

| 키 | 기본 | 내용 |
|---|---|---|
| `omcLabel` | `true` | `[OMC#버전]` 라벨 |
| `updateNotification` | `true` | 라벨에 업데이트 안내 붙이기 |
| `model` | `true` | 모델 이름 |
| `rateLimits` | `true` | **5시간·주간 한도** |
| `contextBar` | `true` | `ctx:` 사용률 |
| `thinking` | `true` | 확장 사고 표시 |
| `promptTime` | `true` | 마지막 프롬프트 시각 |
| `sessionHealth` | `true` | 세션 길이 / 건강도 |
| `showSessionDuration` | `true` | 그중 `session:19m` |
| `showHealthIndicator` | `true` | 그중 🟢🟡🔴 |
| `showCallCounts` | `true` | 우측 도구/에이전트/스킬 호출 수 (`T:24`) |
| `agents` | `true` | **돌고 있는 서브에이전트** |
| `backgroundTasks` | `true` | 백그라운드 작업 |
| `todos` | `true` | 할 일 |
| `activeSkills` · `lastSkill` | `true` | 활성 스킬 / 마지막 스킬 |
| `ralph` · `autopilot` · `prdStory` | `true` | 해당 모드 상태 |
| `profile` | `true` | `CLAUDE_CONFIG_DIR` 프로필 이름 |
| `safeMode` | `true` | ANSI 제거 + ASCII 전용 (터미널 깨짐 방지) |
| `cwd` | `false` | 작업 디렉터리 |
| `gitRepo` · `gitBranch` · `gitStatus` | `false` | git 정보 |
| `hostname` | `false` | **머신 이름 — 다중 머신 · ssh 에 유용** |
| `showTokens` | `false` | 마지막 요청 토큰 (`tok:i1.2k/o340`) |
| `showLastTool` | `false` | 마지막 도구 이름 |
| `useBars` | `false` — **단 focused·full·dense 프리셋이 `true` 로 덮는다.** 기본 프리셋이 focused 라 사실상 켜져 있다 | 퍼센트 대신 막대 게이지 |
| `missionBoard` | `false` | 전체 실행 진척 보드 (별도 줄) |
| `sessionSummary` | `false` | AI 세션 요약. **10턴마다 `claude -p` 를 부르므로 비용이 든다** |
| `apiKeySource` | `false` | API 키 출처 (project/global/env) |
| `permissionStatus` | `false` | 대기 중 권한. 휴리스틱이라 오탐이 잦아 꺼져 있다 |
| `useHyperlinks` | `false` | 경로를 OSC 8 하이퍼링크로 |
| `enterpriseMode` · `showEnterpriseCost` | 자동 | 엔터프라이즈 과금 표시 |

### 형식

| 키 | 기본 | 고를 수 있는 값 |
|---|---|---|
| `agentsFormat` | `multiline` | `count` `codes` `codes-duration` `detailed` `descriptions` `tasks` `multiline` |
| `agentsMaxLines` | `5` | multiline 일 때 최대 줄 수 |
| `modelFormat` | `versioned` | `short` `versioned` `full` |
| `cwdFormat` | `relative` | `relative` `absolute` `folder` |
| `gitInfoPosition` | `above` | `above` `below` |
| `thinkingFormat` | `text` | `bubble` `brain` `face` `text` |
| `callCountsFormat` | `auto` | `auto` `emoji` `ascii` |
| `maxOutputLines` | `4` (minimal 2 · full 12 · dense 6) | 전체 출력 줄 수 상한 (입력창이 줄어드는 걸 막는다). 넘치면 `... (+N lines)` |

## 그 밖의 최상위 키

| 키 | 기본 | 내용 |
|---|---|---|
| `preset` | `focused` | 위 5종 |
| `locale` | `en` | `en` `zh-CN` **만** 지원 |
| `labels` | 아래 참조 | 라벨 문자열 직접 지정 — 한국어로 바꾸려면 여기 |
| `thresholds.contextWarning` | `70` | 노란색 전환 % |
| `thresholds.contextCompactSuggestion` | `80` | compact 권유 % |
| `thresholds.contextCritical` | `85` | 빨간색 전환 % |
| `thresholds.ralphWarning` | `7` | ralph 반복 경고 회차 |
| `contextLimitWarning.threshold` | `80` | 경고 배너 % |
| `contextLimitWarning.autoCompact` | `false` | 넘으면 `/compact` 자동 예약 |
| `staleTaskThresholdMinutes` | `10` | 이 시간 넘게 멈춘 작업을 stale 로 |
| `usageApiPollIntervalMs` | `90000` | 사용량 API 폴링 간격 |
| `maxWidth` | 없음 | 출력 최대 열 수 |
| `wrapMode` | `truncate` | `truncate` (말줄임) 또는 `wrap` (` \| ` 경계에서 줄바꿈) |
| `elementOrder` | 없음 | 메인 줄 요소 순서 |
| `layout` | 없음 | `line1` / `main` / `detail` 그룹별 순서·배치 |
| `missionBoard` | 꺼짐 | `enabled` `maxMissions` `maxAgentsPerMission` `maxTimelineEvents` `persistCompletedForMinutes` |
| `rateLimitsProvider` | 없음 | 한도를 직접 계산하는 외부 명령 (`type` `command` `timeoutMs` `periods`) |

`labels` 로 바꿀 수 있는 문자열: `context`(ctx) `tokens`(tok) `tool`(T)
`agent`(A) `skill`(S) `ralph` `background`(bg) `thinking` `model`
`staged`(+) `modified`(!) `untracked`(?) `ahead`(⇡) `behind`(⇣).

## layout — 순서 바꾸기

프리셋이 on/off 를, `layout` 이 순서와 배치를 정한다. 기본 순서는 이렇다.

```
line1   hostname cwd gitRepo gitBranch gitStatus apiKeySource profile
main    omcLabel model enterpriseCost rateLimits customBuckets permission
        thinking promptTime session tokens ralph autopilot prd skills
        lastSkill contextBar agents background callCounts lastTool
        sessionSummary
detail  missionBoard agents contextWarning payloadWarning todos
```

요소를 그룹 사이로 옮길 수 있다 (예: `contextBar` 를 `main` 에서 `line1` 로).

## HUD 를 아예 끄려면

`~/.claude/.omc-config.json` 의 `hudEnabled` 를 `false` 로 두면 `omc setup` 이
statusLine 설치를 건너뛴다. 이미 설치된 뒤라면 `settings.json` 의 `statusLine`
키를 지우면 된다.
