#!/usr/bin/env python3
"""에이전트의 쓰기·스테이징·비밀값 노출을 실행 전에 막는다 (PreToolUse 훅).

설치 위치는 ~/.local/bin/agent-guard (install.sh 가 링크). Claude Code 의
user 스코프 settings.json 이 부르므로 모든 프로젝트·모든 머신에서 같은 규칙이 돈다.
훅 형식이 같은 Codex 도 그대로 부를 수 있다 (docs/hooks.md).

막는 것 두 가지.
  1. 보호 경로 — 프로젝트가 .claude/guard.json 에 적는다. 없으면 이 규칙은 꺼진다.
       {"protected_paths": ["assessment/data/", "docs/project/"]}
     쓰기·스테이징만 막고 읽기는 통과한다 (측정·채점이 거기서 도는 프로젝트가 있다).
  2. 비밀값 파일 (.env* · *.key · credentials) — 어디서나 같은 규칙.
     써도 되지만 보여주면 안 된다. 보여준다 = 내용이 stdout·대화기록·다른 파일로
     흐른다. 그걸 정하는 것은 파일 이름이 아니라 그 앞의 동사다.
       통과  ls · stat · test · git ls-files · source · uv run --env-file …
             (메타데이터 · 환경 적재)
       차단  cat · head · sed · cp · mv · vi · git add · git show · base64 …  (내용이 흐른다)

.gitignore 는 `git add -f` 를 막지 못하고, permissions.deny 는 Read 도구만 본다.
이 훅은 에이전트 경로의 2차 방어다. 커밋 시점은 pre-commit(gitleaks 등)이 잡는다.

과잉 차단은 조용하지 않다 — 막힌 사람은 훅을 끈다. 그래서 heredoc·인터프리터 `-c` 본문
(코드와 글)은 이름 검사에서 빼고, 검색 명령의 따옴표 속 패턴은 패턴으로 본다. 다만 따옴표
속이 비밀값 경로 그 자체면(`head ".env.local"`) 패턴이 아니라 경로다 — 2026-09-04 리뷰가
실행으로 확인한 우회. 받아들이는 잔여 위험은 docs/guard.md.

종료코드 2 = 차단(사유는 stderr 로 Claude 에게 전달). 그 외 = 통과.
훅 자체가 죽으면 1 로 끝내며 사유를 남긴다 — 통과하되 조용하지는 않다.
시험: scripts/test-guard.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CONFIG_NAME = ".claude/guard.json"
DEFAULT_ALLOW_SUBSTRINGS = ("README.md",)  # 보호 경로 안에서도 쓸 수 있는 파일

# 비밀값 파일 이름. `.env.example` 류는 비밀값이 아니다.
#   *.key 는 파일 이름일 때만 — 뒤에 코드 구두점이 오면 속성 접근이다 (`cfg.key,` · `int(ref.key)`).
#   credentials 는 경로 모양일 때만 — `~/.aws/credentials` · `.credentials.json` ·
#   `application_default_credentials.json`. 맨 단어 `rg credentials` 는 검색어다.
PROTECTED_FILES = re.compile(
    r"""(?<![\w.])\.env(?!\.(?:example|sample|template|dist)\b)(\.[\w.-]+)?\b
      | \.key\b(?!\s*[(\[}=,:\)\]])(?!\.)(?!\s+(?:for|if|in|==|!=)\b)
      | (?<=[/.])[\w-]*credentials\b
      | (?<![\w.])[\w-]*credentials\.\w+
    """,
    re.VERBOSE,
)

# 비밀값 파일 이름이 나와도 되는 동사 — 메타데이터만 보거나 환경에 올린다.
SECRET_SAFE_VERB = re.compile(
    r"^\s*(?:"
    r"ls|ll|stat|test|\[\[?|file|du|wc|realpath|readlink|basename|dirname|chmod|chown"
    r"|\.|source|dotenv|direnv"
    r"|git\s+(?:ls-files|check-ignore|log|status)"
    r")(?:\s|$)"
)
# `git log` 는 메타데이터지만 패치를 찍으면 내용이다.
GIT_LOG_PATCH = re.compile(
    r"^\s*git\s+log\b.*(?:\s-[A-Za-z]*p\b|--patch\b|--full-diff\b|\s-[SG]\S)"
)
# `--env-file X` 는 정의상 환경 적재다 (uv · python-dotenv · node · docker).
ENV_FILE_FLAG = re.compile(r"--env-file(?:=|\s+)\S+")
# source 뒤에 환경을 통째로 쏟는 명령
SOURCE_VERB = re.compile(r"^\s*(?:\.|source)\s+")
ENV_DUMP = re.compile(r"^\s*(?:env|printenv|export\s+-p|set|declare\s+-x|typeset\s+-x)\s*$")
# cp · mv 는 대상이 비밀값 파일이어도 원본이 아니면 아무것도 보여주지 않는다
# (`cp .env.example .env.local`).
COPY_VERB = re.compile(r"^\s*(?:cp|mv)\s+(.*)$")
# JSON·설정 질의 도구의 `.key` 는 질의지 파일이 아니다 (`jq -r .key out.json`).
QUERY_VERB = re.compile(r"^\s*(?:jq|yq|gojq|redis-cli|consul|etcdctl)\b")

# "순수 검색" 명령 — 따옴표 속은 경로가 아니라 패턴이다. echo·printf 의 따옴표 속은 문구다.
SEARCHER = re.compile(
    r"^\s*(?:"
    r"grep|rg|egrep|fgrep|ag|find|fd|ack"
    r"|git\s+(?:log|grep|diff|show|ls-files)"
    r"|head|tail|sort|uniq|wc|cut|awk"
    r"|sed(?!\s*-i)"
    r"|xargs\s+grep"
    r"|echo|printf"
    r")\b"
)

# 스테이징 명령과, 보호 경로를 향해 쓰는 명령들. sed 는 -i 가 있을 때만 쓰기다.
GIT_STAGE = re.compile(r"\bgit\s+(add|stage|commit)\b")
DATA_MUTATOR_CMD = re.compile(
    r"^\s*(sed|tee|dd|cp|rsync|mv|rm|truncate|shred|unzip|tar|install|touch|gzip|ln|mkdir)\b"
)
SED_INPLACE = re.compile(r"(?:^|\s)(?:-i|--in-place)\b")

# 쓰기 리다이렉트의 대상만 본다. `>&2` · `2>&1` 은 fd 정리다. `&>` `>|` 도 쓰기다.
REDIRECT_WRITE = re.compile(r"(?:(?<![&<])&>>?|(?<!&)>>|(?<!&)>\|?)\s*(?!&)([^\s;|&()]+)")
# 다운로드 명령의 출력 플래그. 명령을 한정하는 이유: `grep -o` 는 전혀 다른 뜻이다.
DOWNLOAD_OUT = re.compile(
    r"^\s*(?:curl|wget|aria2c|http|httpie)\b[^\n]*?"
    r"(?:\s(?:-o|-O|--output|--output-document|--download)[= ]\s*)([^\s;|&()]+)"
)

# 커밋 메시지 안의 경로 이름은 경로가 아니다. `git commit` 이 있을 때만, 소문자 결합
# 플래그(-am · -sm)만 메시지로 본다 — `git add -Am 경로` 의 경로를 지우면 안 된다.
COMMIT_MSG = re.compile(r"(?:-[a-z]*m|--message)(?:\s+|=)?(?:\"[^\"]*\"|'[^']*'|\S+)")
GIT_COMMIT = re.compile(r"\bgit\s+commit\b")

# heredoc: `<<'TAG'` … `TAG`. 따옴표 없는 태그는 $( ) 를 푸니 본문에 그게 있으면 남긴다.
HEREDOC = re.compile(
    r"<<-?\s*(?P<q>[\"']?)(?P<tag>[A-Za-z_][\w-]*)(?P=q)[^\n]*\n"
    r"(?P<body>.*?)^[ \t]*(?P=tag)[ \t]*$",
    re.M | re.S,
)
# 셸이 아닌 인터프리터의 `-c '…'` · `-e '…'` 본문. bash -c · sh -c · ssh 는 셸 명령이라 빼지 않는다.
INTERP_CODE = re.compile(
    r"\b(?:python[\d.]*|node|ruby|perl)\b[^\n|;&]*?\s-[ce]\s+(?P<code>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
)
# 셸의 `-c '…'` · `eval '…'` · here-string · ssh 의 원격 명령은 안쪽이 그대로 셸 명령이다 —
# 풀어서 다시 판정한다.
SHELL_CODE = re.compile(
    r"(?:\b(?:bash|sh|zsh|dash|ksh)\b[^\n|;&]*?\s-[a-z]*c\s+|\beval\s+|<<<\s*|\bssh\b[^\n|;&]*?\s)"
    r"(?P<code>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
)
# 따옴표 속이 경로 하나인가 — 공백도 정규식·글롭 문자도 없다. `'\.env|\.key'` 는 패턴이다.
PATHLIKE = re.compile(r"^[\w./~\-]+$")
# 앞에 붙는 환경 대입·래퍼·실행기·제어 키워드. `FOO=1 timeout 60 uv run …` 의 동사는 그 뒤고,
# `do [ -f $f ]` 의 동사는 `[` 다.
INLINE_ASSIGNS = re.compile(r"^\s*((?:[A-Za-z_]\w*=\S*\s+)+)")
LEADING_WRAPPERS = re.compile(
    r"^\s*(?:[A-Za-z_]\w*=\S*\s+|timeout\s+\S+\s+|sudo\s+|command\s+|nice\s+|env\s+"
    r"|(?:uv|poetry|pipx|npx|pdm|hatch)\s+run\s+"
    r"|do\s+|then\s+|else\s+|if\s+|while\s+|until\s+|!\s+|\{\s+|\(\s*)*"
)
# 변수에 넣은 경로는 뒤에서 `$f` 로 쓰인다 — 대입과 for 를 보고 치환해서 따라간다.
ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)=(\S*)\s*$")
FOR_IN = re.compile(r"^\s*for\s+([A-Za-z_]\w*)\s+in\s+(.*)$")
MAX_COMMAND = 64_000  # 이보다 길면 정규식 비용이 의미를 잃는다 — 잘라서 본다


def _has_substitution(s: str) -> bool:
    return "$(" in s or "`" in s or "${" in s


def _strip_bodies(text: str) -> str:
    """heredoc 본문과 인터프리터 `-c` 본문을 지운다 — 코드와 글이지 셸 인자가 아니다.
    `<<EOF` 줄 자체는 남겨 그 줄의 리다이렉트 대상은 검사한다."""

    def _heredoc(m: re.Match[str]) -> str:
        if not m.group("q") and _has_substitution(m.group("body")):
            return m.group(0)  # 셸이 본문을 치환한다 — 숨긴 명령일 수 있다
        return m.group(0)[: m.start("body") - m.start()] + m.group("tag")

    text = HEREDOC.sub(_heredoc, text)

    def _code(m: re.Match[str]) -> str:
        code = m.group("code")
        if code[0] == '"' and _has_substitution(code):
            return m.group(0)
        return m.group(0)[: m.start("code") - m.start()] + "''"

    return INTERP_CODE.sub(_code, text)


def split_segments(text: str) -> list[str]:
    """`|` `||` `;` `&&` 줄바꿈으로 나눈다 — 따옴표 안은 나누지 않는다.
    `grep -E 'a|\\.env'` 의 `|` 는 패턴이지 파이프가 아니다."""
    out, buf, q, i = [], [], "", 0
    while i < len(text):
        c = text[i]
        if q:
            buf.append(c)
            if c == q:
                q = ""
            elif c == "\\" and q == '"' and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 1
        elif c in "\"'":
            q = c
            buf.append(c)
        elif c == "\\" and i + 1 < len(text):
            buf.append(c)
            buf.append(text[i + 1])
            i += 1
        elif c == "\n" or c == ";":
            out.append("".join(buf))
            buf = []
        elif c == "|" or c == "&":
            if i + 1 < len(text) and text[i + 1] == c:
                i += 1
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    out.append("".join(buf))
    return [s for s in out if s.strip()]


def _strip_quoted(text: str, aggressive: bool) -> str:
    """따옴표 속을 지운다. 남기는 것 셋 —
    · 속이 비밀값 경로 그 자체 (`head ".env.local"`) — 공백·정규식 문자 없는 경로 하나일 때만
    · `$( ) ${ }` 백틱이 든 것 — `"$(cat .env.local)"` 같은 치환이 숨어 있다
      (작은따옴표는 `$(` `${` 만 — 큰따옴표 안의 작은따옴표일 수 있어서. 백틱은 마크다운이다)
    · aggressive 가 아니면 공백 없는 것 — 공백이 있으면 경로가 아니라 문구·패턴이다
      (`gh pr create --body "see .env docs"`)"""

    def _keep_or_blank(m: re.Match[str], subst) -> str:
        inner = m.group(1)
        if subst(inner) or (PATHLIKE.match(inner) and PROTECTED_FILES.search(inner)):
            return m.group(0)
        return " " if (aggressive or re.search(r"\s", inner)) else m.group(0)

    # 작은따옴표 안에서 백틱은 글자다 (마크다운 문구를 sed 로 고치다 실제로 막혔다). `$(` `${` 만
    # 남긴다 — 큰따옴표 안에 든 작은따옴표일 가능성에 대한 보험이다.
    text = re.sub(r"'([^']*)'", lambda m: _keep_or_blank(m, lambda i: "$(" in i or "${" in i), text)
    return re.sub(r'"((?:[^"\\]|\\.)*)"', lambda m: _keep_or_blank(m, _has_substitution), text)


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token.strip("'\"")


def _write_targets(whole: str) -> list[str]:
    """쓰기 리다이렉트·다운로드 대상. 언쿼트해서 본다 — 따옴표에 숨어도 실제 경로다."""
    targets = [_unquote(t) for t in REDIRECT_WRITE.findall(whole)]
    for seg in split_segments(whole):
        if dl := DOWNLOAD_OUT.match(LEADING_WRAPPERS.sub("", seg, count=1)):
            targets.append(_unquote(dl.group(1)))
    return targets


# ── 프로젝트 설정 ──────────────────────────────────────────────────────────


def load_config(payload: dict) -> dict:
    """payload 의 cwd(먼저 CLAUDE_PROJECT_DIR)에서 위로 올라가며 .claude/guard.json 을 찾는다.
    없거나 깨져 있으면 빈 설정 — 비밀값 규칙만 남는다. 타입이 틀린 항목은 무시한다."""
    starts = []
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        starts.append(Path(os.environ["CLAUDE_PROJECT_DIR"]))
    if isinstance(payload.get("cwd"), str) and payload["cwd"]:
        starts.append(Path(payload["cwd"]))
    raw: dict = {}
    for start in starts:
        found = next(
            (d / CONFIG_NAME for d in (start, *start.parents) if (d / CONFIG_NAME).is_file()), None
        )
        if found is None:
            continue
        try:
            loaded = json.loads(found.read_text(encoding="utf-8"))
            raw = loaded if isinstance(loaded, dict) else {}
        except Exception:  # noqa: BLE001 — 설정이 깨졌다고 훅이 죽으면 안 된다
            raw = {}
        break
    paths = raw.get("protected_paths")
    allow = raw.get("allow_substrings", DEFAULT_ALLOW_SUBSTRINGS)
    return {
        "protected_paths": [p for p in paths if isinstance(p, str) and p]
        if isinstance(paths, list)
        else [],
        "allow_substrings": tuple(a for a in allow if isinstance(a, str) and a)
        if isinstance(allow, (list, tuple))
        else DEFAULT_ALLOW_SUBSTRINGS,
    }


# ── 판정 ──────────────────────────────────────────────────────────────────


def data_reason(text: str, cfg: dict) -> str | None:
    """보호 경로가 든 토큰이 있나. 예외(README.md)는 명령 전체가 아니라 그 토큰 안에서만 본다 —
    `git add assessment/data/x README.md` 의 README 가 x 를 풀어주면 안 된다."""
    allow = cfg["allow_substrings"]
    for pfx in cfg["protected_paths"]:
        for tok in re.findall(r"\S+", text):
            if pfx in tok and not any(a in tok for a in allow):
                return (
                    f"'{pfx}' 안의 것은 쓰거나 커밋하지 않는다 (.claude/guard.json 의 보호 경로). "
                    "읽기는 된다. 배치 방법은 그 디렉토리의 README 참고."
                )
    return None


SECRET_REASON = (
    "비밀값 파일(.env · *.key · credentials)은 내용을 보여주지 않는다. "
    "존재 확인(ls · test · git ls-files)과 환경 적재(source · --env-file)는 된다. "
    "값이 필요하면 환경변수로 올려 쓰고, 이름만 문서에 적는다."
)


def _bind(bound: dict[str, str], name: str, value: str) -> None:
    if PROTECTED_FILES.search(_unquote(value)):
        bound[name] = _unquote(value)


def _substitute(seg: str, bound: dict[str, str]) -> str:
    for name, val in bound.items():
        seg = re.sub(r"\$\{?" + name + r"\}?(?!\w)", val, seg)
    return seg


def secret_reason_for_bash(raw: str) -> str | None:
    shell = _strip_bodies(raw)
    whole = COMMIT_MSG.sub(" ", shell) if GIT_COMMIT.search(shell) else shell

    if any(PROTECTED_FILES.search(t) for t in _write_targets(whole)):
        return SECRET_REASON

    sourced = False
    bound: dict[str, str] = {}  # 변수 이름 → 비밀값 경로
    for seg in split_segments(whole):
        seg = _substitute(seg, bound)
        if m := ASSIGN.match(seg):
            _bind(bound, m.group(1), m.group(2))
            continue
        if m := FOR_IN.match(seg):
            for w in m.group(2).split():
                if PROTECTED_FILES.search(_unquote(w)):
                    _bind(bound, m.group(1), w)
                    break
            continue
        if m := INLINE_ASSIGNS.match(seg):  # `ENVF=.env.local bash -c 'cat $ENVF'`
            for a in m.group(1).split():
                name, _, val = a.partition("=")
                _bind(bound, name, val)
            seg = _substitute(seg, bound)
        for sc in SHELL_CODE.finditer(seg):  # `bash -c 'cat .env.local'` · `ssh host 'cat .env'`
            if secret_reason_for_bash(_unquote(sc.group("code"))):
                return SECRET_REASON
        body = LEADING_WRAPPERS.sub("", seg, count=1)
        if ENV_DUMP.match(body) and sourced:
            return SECRET_REASON
        text = _strip_quoted(body, aggressive=bool(SEARCHER.match(body)))
        text = ENV_FILE_FLAG.sub(" ", text)
        if QUERY_VERB.match(body):
            text = re.sub(r"\.key\b", " ", text)
        if not PROTECTED_FILES.search(text):
            continue
        if SOURCE_VERB.match(body):
            sourced = True
            continue
        if SECRET_SAFE_VERB.match(body) and not GIT_LOG_PATCH.match(body):
            continue
        if cp := COPY_VERB.match(body):
            args = [a for a in cp.group(1).split() if not a.startswith("-")]
            if args and not any(PROTECTED_FILES.search(_unquote(a)) for a in args[:-1]):
                continue  # 원본이 비밀값이 아니면 보여주는 것이 없다
        return SECRET_REASON
    return None


def data_reason_for_bash(raw: str, cfg: dict) -> str | None:
    if not cfg["protected_paths"]:
        return None
    shell = _strip_bodies(raw)
    whole = COMMIT_MSG.sub(" ", shell) if GIT_COMMIT.search(shell) else shell
    parts = [whole] if GIT_STAGE.search(whole) else []
    parts += _write_targets(whole)
    for seg in split_segments(whole):
        body = LEADING_WRAPPERS.sub("", seg, count=1)
        m = DATA_MUTATOR_CMD.match(body)
        if not m:
            continue
        if m.group(1) == "sed" and not SED_INPLACE.search(body):
            continue  # `sed 'script' file` 은 stdout 으로 흘려보내는 읽기다
        parts.append(body.replace("'", "").replace('"', ""))  # 따옴표 친 대상도 대상이다
    return data_reason(" ".join(parts), cfg) if parts else None


def decide(payload: dict) -> str | None:
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    cfg = load_config(payload)

    if tool in ("Read", "Write", "Edit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not isinstance(path, str) or not path:
            return None
        if tool != "Read" and (r := data_reason(path, cfg)):
            return r
        return SECRET_REASON if PROTECTED_FILES.search(path) else None
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or not cmd:
            return None
        cmd = cmd[:MAX_COMMAND]
        return data_reason_for_bash(cmd, cfg) or secret_reason_for_bash(cmd)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — 입력을 못 읽으면 조용히 통과시킨다
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        reason = decide(payload)
    except Exception as e:  # noqa: BLE001 — 훅이 죽으면 통과하되, 조용히는 아니다
        print(f"agent-guard 내부 오류로 판정을 못 했다 (통과시킴): {e!r}", file=sys.stderr)
        return 1
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
