# 가드 훅 — 비밀값 노출 · 보호 경로 쓰기를 실행 전에 막는다

`agent/guard.py` → `~/.local/bin/agent-guard`. `claude/settings.json` 의 `PreToolUse`
(`Read|Write|Edit|NotebookEdit|Bash`) 가 부르므로 **모든 프로젝트 · 모든 머신**에서 같은 규칙이 돈다.
시험은 `python3 scripts/test-guard.py`.

## 왜 저장소가 소유하나

원래는 프로젝트마다 `.claude/hooks/block-protected-paths.py` 를 복사해 뒀다. 두 사본이 두 커밋만큼
갈라져 있었고, 한쪽에서 고친 오차단이 다른 쪽에는 남았다. 2026-09-04 기준 그 훅이 실제로 막은
명령 30건을 세션 로그에서 재생해 보니 **18건이 정상 작업**이었다 — `.key` 정규식은 세 번을 고쳐도
새 모양(`{r.key!r}` · `r.key⏎`)이 계속 나왔다. 막힌 사람은 훅을 끈다. 그게 이런 훅에는 가장 나쁜
결과다.

그래서 판정 로직은 한 벌만 두고, 프로젝트는 "무엇을 보호할지"만 적는다.

## 두 가지 규칙

### 1. 보호 경로 — 프로젝트가 정한다

```json
// <프로젝트>/.claude/guard.json
{"protected_paths": ["assessment/data/", "docs/project/"]}
```

훅은 payload 의 `cwd`(먼저 `CLAUDE_PROJECT_DIR`)에서 위로 올라가며 이 파일을 찾는다.
없으면 이 규칙은 꺼진다. 깨져 있어도 훅이 죽지 않고 비밀값 규칙만 남는다.

| 막는다 | 통과한다 |
|---|---|
| `git add` · `git commit` 에 경로가 들어감 (`-f` · `-Am` 포함) | `ls` · `du` · `cat` · `md5sum` 등 읽기 |
| `>` `>>` 리다이렉트 대상 (`2>` 도 대상이 경로면 쓰기) | `2>/dev/null` · `2>&1` 같은 fd 정리 |
| `curl -o` `wget -O` 출력 대상 | `grep -o` (전혀 다른 뜻) |
| `sed -i` · `tee` · `cp` · `mv` · `rm` · `tar` … 의 대상 | `sed 's/x/y/' 파일` (stdout 으로 흐르는 읽기) |
| `Write` · `Edit` · `NotebookEdit` 의 대상 | 커밋 메시지 안의 경로 이름 |
| | 경로 안의 `README.md` (`allow_substrings` 로 바꿀 수 있다) |

읽기를 막지 않는 이유: 측정·채점이 그 디렉토리에서 도는 프로젝트가 있다. 언급만으로 막으면
작업이 성립하지 않는다.

### 2. 비밀값 파일 — 어디서나 같다

대상은 `.env` · `.env.*` (단 `.env.example` `.sample` `.template` `.dist` 는 제외) · `*.key` · 경로 모양의 `credentials` (`~/.aws/credentials` · `.credentials.json` · `*_credentials.json`).

원칙 하나: **써도 되지만 보여주면 안 된다.** 보여준다 = 내용이 stdout · 대화기록 · 다른 파일로
흐른다. 그걸 정하는 것은 파일 이름이 아니라 **그 앞의 동사**다.

| 통과 — 메타데이터만 보거나 환경에 올린다 | 차단 — 내용이 흐른다 |
|---|---|
| `ls` `stat` `test` `[` `file` `du` `wc` `realpath` `chmod` | `cat` `head` `tail` `less` `base64` `python x.py .env` |
| `git ls-files` `git check-ignore` `git log -- .env` `git status` | `git add` `git show HEAD -- .env` `git log -p -- .env` |
| `.` `source` `set -a; . .env.local; set +a` | `sed -i` `cp .env.local x` `mv .env.local x` `vi` |
| `uv run --env-file .env.local …` `dotenv -f … run` `direnv` | `> .env.local` `>> .env` (리다이렉트 대상) |
| `cp .env.example .env.local` (원본이 비밀값이 아니면 보여주는 게 없다) | `bash -c 'cat .env.local'` `ssh host 'cat .env'` (안쪽을 풀어 다시 판정) |
| `jq -r .key out.json` (질의 도구의 `.key` 는 질의) | `Read` `Write` `Edit` `NotebookEdit` 도구로 `.env.local` |
| `Read` 도구로 `.env.example` | `cat ~/.aws/credentials` `cat application_default_credentials.json` |

`credentials` 는 경로 모양(`/` 나 `.` 뒤, 또는 `credentials.json`)일 때만 비밀값이다 — `rg credentials` 는 검색어다.

여기에 세 가지 장치가 얹힌다.

- **heredoc · 인터프리터 `-c` 본문은 이름 검사에서 뺀다.** `python - <<'PY'` 안의 `r.key` 는 속성이고,
  `cat >> CLAUDE.md <<'EOF'` 안의 `.env.local` 은 글이다. `<<EOF` 줄 자체는 남겨 그 줄의
  리다이렉트 대상(`cat > .env.local <<EOF`)은 본다. 따옴표 없는 태그(`<<EOF`)나 큰따옴표 `-c` 본문에
  `$(` `${` 백틱이 있으면 셸이 먼저 푸는 것이라 빼지 않는다. `bash -c` 는 셸이라 빼지 않는다.
- **검색 명령의 따옴표 속은 패턴이다.** `grep` `rg` `find` `git log|diff|show` `head` `tail` `echo` `printf`
  등으로 시작하는 segment 는 따옴표 속을 지우고 본다. 그 외 명령은 **공백이 든** 따옴표 span 만 지운다 —
  공백이 있으면 경로가 아니라 문구다 (`gh pr create --body "see .env docs"`). 단 **따옴표 속이 경로 하나**
  (공백도 정규식·글롭 문자도 없음)이고 그게 비밀값 파일이면 어느 명령에서도 남긴다 — `head ".env.local"`
  이 검색 예외로 빠져나가던 구멍이다 (2026-09-04 리뷰). `$(` 가 든 span 도 어느 경우에도 남긴다
  (`echo "$(cat .env.local)"`).
  segment 는 `|` `||` `;` `&&` 줄바꿈으로 나누되 **따옴표 안은 나누지 않는다** — 예전엔
  `grep -E 'a|\.env'` 의 `|` 에서 갈려 `\.env` 조각이 걸렸다.
- **변수를 따라간다.** `f=.env.local; cat $f` · `ENVF=.env.local bash -c 'cat $ENVF'` ·
  `for f in .env; do cat $f` 는 막고, `for f in .env; do [ -f $f ]` 는 통과한다. source 한 뒤 맨 `env`
  `printenv` `export -p` `set` 은 막는다. `bash -c` · `sh -c` · `eval` · here-string(`<<<`) · `ssh host` 의
  따옴표 본문은 안쪽 명령으로 다시 판정한다 — 셸이라 코드 예외를 주지 않는다.

### 받아들인 잔여 위험

| 통과하는 것 | 왜 그냥 두나 |
|---|---|
| heredoc 안의 python 이 `.env.local` 을 열어 `print` | 키를 환경에만 올리는 로더(`runwith.py`)와 정규식으로 구별할 수 없다. 뒤에 `Read` 도구의 `permissions.deny` 와 pre-commit(gitleaks)이 있다 |
| `source .env.local` 뒤 `python -c 'print(os.environ)'` | 키를 셸에 올리는 것을 허용한 대가. 맨 `env` 류만 막는다 |
| `git add .` `git add -A` `git commit -a` 가 보호 경로를 쓸어 담는 것 | 이름이 안 나오면 못 본다. pre-commit 이 잡는다 |
| `cat .en*.local` · `cat$IFS.env.local` 같은 글롭·IFS 변형 | 이름 매칭의 한계. `cat${IFS}.env.local` · `cp .env* /tmp` 는 막힌다 |
| `~/.ssh/id_rsa` `*.pem` `~/.netrc` `~/.kube/config` | 범위 밖 — 대상은 `.env*` · `*.key` · `credentials` 셋뿐이다 |
| `rm .env.local` · `touch .env.local` | 보여주는 건 아니지만 예전 규칙 그대로 막는다. 필요하면 손으로 |
| Codex · Gemini | Claude Code 의 settings.json 만 부른다. Codex 는 `codex/hooks.snippet.json` 에 같은 항목을 붙일 수 있으나 신뢰 재승인이 필요하다 (`codex/README.md`) |

이 훅은 **2차 방어**다. `.gitignore` 는 `git add -f` 를 못 막고, `permissions.deny` 는 `Read` 도구만
본다. 커밋 시점의 최종 방어는 각 프로젝트의 pre-commit 이다.

## 프로젝트에서 쓰는 법

1. 보호할 경로가 있으면 `.claude/guard.json` 한 줄. 비밀값 규칙은 아무것도 안 해도 돈다.
2. 예전 방식의 `.claude/hooks/block-protected-paths.py` 와 `settings.json` 의 훅 항목은 지운다.
   둘 다 두면 두 번 돌고, 예전 사본의 오차단이 그대로 남는다.
3. **팀 저장소**는 예외 — 팀원에게는 이 dotfiles 가 없다. `agent/guard.py` 를
   `.claude/hooks/block-protected-paths.py` 로 **복사**해 두고 `guard.json` 도 둔다. 내 세션에서는
   전역 훅과 둘 다 돌지만 판정이 같아 무해하다. 갈라짐은 그쪽 시험이 잡는다
   (harness 가 이 경우다 — `tests/unit/test_claude_hook.py`).

훅이 도는지 직접 찔러본다:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"cat .env.local"}}' | agent-guard; echo "rc=$?"   # 2
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la .env.local"}}' | agent-guard; echo "rc=$?" # 0
```

## 규칙을 고칠 때

`scripts/test-guard.py` 에 **막아야 하는 것과 막지 말아야 하는 것을 같은 무게로** 넣는다.
오차단이 나면 그 명령을 통과 케이스로 먼저 넣고(RED), 훅을 고친다(GREEN). 정규식을 넓히는
쪽으로 고치기 전에 "이건 코드/글인가, 검색 패턴인가, 동사가 무엇인가" 를 먼저 묻는다 —
세 장치 중 하나가 이미 답인 경우가 대부분이다.

## Windows

`lapwin` 처럼 네이티브 Windows 에서는 `python3` 와 `$HOME` 확장이 다를 수 있다. 그 머신에서
`./install.sh --check` 와 위 찔러보기로 확인한다. 안 되면 `local/hosts/<호스트>/settings-overlay.json`
에서 훅 명령을 덮어쓴다 (`docs/machines.md`).
