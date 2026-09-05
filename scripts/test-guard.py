#!/usr/bin/env python3
"""agent/guard.py 테스트.  실행: python3 scripts/test-guard.py

이 훅은 두 방향 모두에서 조용히 틀린다. 덜 막으면 비밀값이 새고, 더 막으면
사람이 훅을 끈다 — pipespec 에서 30번 막힌 명령 중 18번이 정상 작업이었고, 그중
`.key` 정규식은 세 번을 고쳐도 새 모양이 계속 나왔다. 그래서 막아야 할 것과
막지 말아야 할 것을 같은 무게로 고정한다.

원칙 하나: **비밀값 파일은 써도 되지만 보여주면 안 된다.** 보여준다 = 내용이
stdout·대화기록·다른 파일로 흐른다. 그걸 정하는 것은 파일 이름이 아니라 동사다.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
HOOK = HERE.parent / "agent" / "guard.py"
BLOCKED = 2  # 훅 규약: 종료코드 2 = 차단(사유는 stderr), 그 외 = 통과


def run(payload: dict, cwd: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    if cwd is not None:
        payload = {**payload, "cwd": cwd}
    e = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=e,
    )


def bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def tool(name: str, path: str) -> dict:
    return {"tool_name": name, "tool_input": {"file_path": path}}


class GuardCase(unittest.TestCase):
    """프로젝트 하나를 흉내 낸다 — .claude/guard.json 이 보호 경로를 정한다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.project = pathlib.Path(cls.tmp.name) / "proj"
        (cls.project / ".claude").mkdir(parents=True)
        (cls.project / ".claude" / "guard.json").write_text(
            json.dumps({"protected_paths": ["assessment/data/", "docs/project/"]}),
            encoding="utf-8",
        )
        cls.sub = cls.project / "src" / "deep"
        cls.sub.mkdir(parents=True)
        cls.bare = pathlib.Path(cls.tmp.name) / "bare"  # guard.json 없는 프로젝트
        cls.bare.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertBlocked(self, payload, cwd=None, msg=""):
        r = run(payload, cwd=str(cwd or self.project))
        self.assertEqual(r.returncode, BLOCKED, f"막혀야 하는데 통과: {msg or payload}\n{r.stderr}")
        self.assertTrue(r.stderr.strip(), "차단 사유가 stderr 에 있어야 한다")

    def assertPasses(self, payload, cwd=None, msg=""):
        r = run(payload, cwd=str(cwd or self.project))
        self.assertNotEqual(r.returncode, BLOCKED, f"막으면 안 되는데 막힘: {msg or payload}\n{r.stderr}")


# ── 데이터(보호 경로) — 쓰기·스테이징만 막는다 ─────────────────────────────

class ProtectedPaths(GuardCase):
    def test_보호_경로_스테이징은_막는다(self):
        self.assertBlocked(bash("git add assessment/data/cases/case_0001/tokens.json"))
        self.assertBlocked(bash("git add -f assessment/data/cases/"))
        self.assertBlocked(bash("git add -Am assessment/data/cases"))

    def test_보호_경로로의_리다이렉트는_막는다(self):
        self.assertBlocked(bash("echo x > assessment/data/cases/foo.json"))
        self.assertBlocked(bash("uv run python x.py >> assessment/data/cleaned/out.json"))
        self.assertBlocked(bash("pytest 3> assessment/data/out.json"))

    def test_보호_경로로의_다운로드는_막는다(self):
        self.assertBlocked(bash("curl -o assessment/data/cases/evil.json http://x"))
        self.assertBlocked(bash("curl -o 'assessment/data/cases/evil.json' http://x"))

    def test_보호_경로를_바꾸는_명령은_막는다(self):
        self.assertBlocked(bash("sed -i 's/a/b/' assessment/data/cases/x.json"))
        self.assertBlocked(bash("tee assessment/data/x"))
        self.assertBlocked(bash("cp foo assessment/data/"))
        self.assertBlocked(bash("cp foo 'assessment/data/x'"), msg="따옴표 친 대상도 대상이다")

    def test_보호_경로에_Write_는_막는다(self):
        self.assertBlocked(tool("Write", "assessment/data/cases/case_0001/expected.json"))
        self.assertBlocked(tool("Edit", str(self.project / "docs/project/notes.md")))

    def test_README_예외는_그_경로_토큰에만_걸린다(self):
        self.assertBlocked(bash("git add assessment/data/x README.md"))
        self.assertBlocked(bash("cp README.md /tmp; git add assessment/data/x"))
        self.assertPasses(bash("git add assessment/data/README.md"))

    def test_앰퍼샌드_리다이렉트와_래퍼_뒤의_다운로드도_대상이다(self):
        self.assertBlocked(bash("echo x &> assessment/data/o.json"))
        self.assertBlocked(bash("echo x >| assessment/data/o.json"))
        self.assertBlocked(bash("sudo curl -o assessment/data/o.json http://y"))

    def test_NotebookEdit_은_notebook_path_를_본다(self):
        self.assertBlocked({"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "assessment/data/nb.ipynb"}})
        self.assertBlocked({"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "/x/.env.local"}}, cwd=self.bare)

    def test_두_번째_보호_경로도_같은_규칙이다(self):
        self.assertBlocked(bash("git add docs/project/spec.md"))

    def test_보호_경로_읽기는_통과한다(self):
        self.assertPasses(bash("du -sh assessment/data/cases 2>/dev/null"))
        self.assertPasses(bash("ls -la assessment/data/cases | head"))
        self.assertPasses(bash("uv run python scripts/run_all.py --cases assessment/data/cases_v2"))
        self.assertPasses(bash("grep -o 'assessment/data/[^ ]*' build.log"))
        self.assertPasses(bash("sed 's/x/y/' assessment/data/cases/x.json"), msg="-i 없는 sed 는 읽기")
        self.assertPasses(bash("md5sum $H/assessment/data/score_v2.py"))

    def test_README_는_보호_경로_안에서도_쓸_수_있다(self):
        self.assertPasses(bash("cat assessment/data/README.md"))
        self.assertPasses(tool("Write", "assessment/data/README.md"))

    def test_fd_정리와_heredoc_의_부등호는_리다이렉트가_아니다(self):
        self.assertPasses(bash("uv run pytest -q 2>&1 | tail -3"))
        self.assertPasses(bash('python - <<PY\nif n >= 2:\n    print("assessment/data/cases")\nPY'))
        self.assertPasses(bash("uv run pytest -q > /tmp/out.txt"))
        self.assertPasses(bash("curl -o /tmp/x.json http://example.com"))

    def test_커밋_메시지_속_경로_이름은_경로가_아니다(self):
        self.assertPasses(bash('git commit -m "docs(assessment): assessment/data/ 배치 절차"'))
        self.assertPasses(bash('git commit -m"fix: .env 문서 정리"'))
        self.assertPasses(bash('git commit -am "fix: .env 정리"'))

    def test_guard_json_은_하위_디렉토리에서도_찾는다(self):
        self.assertBlocked(bash("git add assessment/data/x"), cwd=self.sub)

    def test_CLAUDE_PROJECT_DIR_가_있으면_그걸_먼저_본다(self):
        r = run(bash("git add assessment/data/x"), cwd=str(self.bare),
                env={"CLAUDE_PROJECT_DIR": str(self.project)})
        self.assertEqual(r.returncode, BLOCKED)

    def test_guard_json_이_없으면_데이터_규칙은_꺼진다(self):
        self.assertPasses(bash("git add assessment/data/x"), cwd=self.bare)
        self.assertPasses(tool("Write", "assessment/data/x.json"), cwd=self.bare)

    def test_guard_json_이_깨져_있으면_비밀값_규칙만_남는다(self):
        broken = pathlib.Path(self.tmp.name) / "broken"
        (broken / ".claude").mkdir(parents=True)
        (broken / ".claude" / "guard.json").write_text("{ 깨짐", encoding="utf-8")
        self.assertPasses(bash("git add assessment/data/x"), cwd=broken)
        self.assertBlocked(bash("cat .env.local"), cwd=broken)


# ── 비밀값 파일 — 어디서나 같은 규칙 ────────────────────────────────────────

class SecretsBlocked(GuardCase):
    """보여주는 것 — 내용이 stdout·대화기록·다른 파일로 흐르는 명령."""

    def test_비밀값_파일_쓰기_도구는_막는다(self):
        self.assertBlocked(tool("Write", ".env.local"), cwd=self.bare)
        self.assertBlocked(tool("Edit", "/abs/path/.env"), cwd=self.bare)
        self.assertBlocked(tool("Read", ".env.local"), cwd=self.bare)
        self.assertBlocked(tool("Read", "/srv/app/.env"), cwd=self.bare)
        self.assertBlocked(tool("Read", "certs/server.key"), cwd=self.bare)

    def test_내용을_출력하는_동사는_막는다(self):
        for cmd in (
            "cat .env.local",
            "head -c 20 .env.local",
            "tail .env",
            "less .env.local",
            "cat ~/.env.local",
            "cat \".env.local\"",
            "[ -f .env.local ] && cat .env.local",
            "base64 .env.local",
            "python scripts/dump.py .env.local",
        ):
            self.assertBlocked(bash(cmd), cwd=self.bare, msg=cmd)

    def test_내용을_바꾸거나_옮기는_동사는_막는다(self):
        for cmd in (
            "sed -i 's/x/y/' .env.local",
            "cp secrets.key backup/ > log.txt",
            "cp /etc/ssl/server.key .",
            "mv .env.local /tmp/",
            "vi .env.local",
            "git add .env",
            "git show HEAD -- .env.local",
        ):
            self.assertBlocked(bash(cmd), cwd=self.bare, msg=cmd)

    def test_비밀값_파일로의_리다이렉트는_막는다(self):
        self.assertBlocked(bash("grep -r password src > '.env.local'"), cwd=self.bare)
        self.assertBlocked(bash("grep secret src >> '.env.prod.local'"), cwd=self.bare)
        self.assertBlocked(bash("echo KEY=x > .env.local"), cwd=self.bare)
        self.assertBlocked(bash("cat > .env.local <<'EOF'\nKEY=x\nEOF"), cwd=self.bare,
                           msg="heredoc 본문은 빼도 대상은 본다")

    def test_명령_치환으로_숨긴_읽기는_막는다(self):
        self.assertBlocked(bash('rg x "$(cat .env.local)"'), cwd=self.bare)
        self.assertBlocked(bash('echo "$(cat .env.local)"'), cwd=self.bare)
        self.assertBlocked(bash("rg x $(cat .env.local)"), cwd=self.bare)
        self.assertBlocked(bash('python -c "print(\'$(cat .env.local)\')"'), cwd=self.bare,
                           msg="큰따옴표 -c 안의 $( ) 는 셸이 먼저 푼다")
        self.assertBlocked(bash("cat <<EOF\n$(cat .env.local)\nEOF"), cwd=self.bare,
                           msg="따옴표 없는 heredoc 은 $( ) 를 푼다")

    def test_따옴표로_감싼_경로는_검색_동사_뒤에서도_경로다(self):
        for cmd in (
            'head ".env.local"',
            "tail -n 200 '.env.local'",
            "sed -n '1,99p' '.env.local'",
            "awk '{print}' '.env.local'",
            "grep '' '.env.local'",
            "git show HEAD -- '.env.local'",
            "git diff --no-index '.env.local' /dev/null",
        ):
            self.assertBlocked(bash(cmd), cwd=self.bare, msg=cmd)

    def test_셸_의_c_본문은_셸_명령이다(self):
        for cmd in (
            "bash -c 'cat .env.local'",
            'sh -c "cat .env.local"',
            "env bash -c 'cat .env.local'",
            "ssh host 'cat .env.local'",
        ):
            self.assertBlocked(bash(cmd), cwd=self.bare, msg=cmd)

    def test_git_log_은_패치를_찍으면_내용이_흐른다(self):
        self.assertBlocked(bash("git log -p -- .env.local"), cwd=self.bare)
        self.assertBlocked(bash("git log -1 --patch certs/server.key"), cwd=self.bare)
        self.assertPasses(bash("git log --oneline --all -- .env.local | head -3"), cwd=self.bare)

    def test_인라인_대입도_변수로_묶인다(self):
        self.assertBlocked(bash("ENVF=.env.local bash -c 'cat $ENVF'"), cwd=self.bare)
        self.assertBlocked(bash("FOO=.env.local BAR=x cat $FOO"), cwd=self.bare)

    def test_점_없는_credentials_도_비밀값이다(self):
        self.assertBlocked(bash("cat ~/.aws/credentials"), cwd=self.bare)
        self.assertBlocked(tool("Read", "/home/x/.config/gcloud/application_default_credentials.json"), cwd=self.bare)

    def test_변수에_숨긴_경로도_따라간다(self):
        self.assertBlocked(bash("f=.env.local; cat $f"), cwd=self.bare)
        self.assertBlocked(bash('F=".env.local"\ncat "${F}"'), cwd=self.bare)
        self.assertBlocked(bash("for f in .env $H/.env; do cat $f; done"), cwd=self.bare)

    def test_환경에_올린_뒤_통째로_덤프하면_막는다(self):
        self.assertBlocked(bash("set -a; . .env.local; set +a; env"), cwd=self.bare)
        self.assertBlocked(bash("source .env.local && printenv"), cwd=self.bare)
        self.assertBlocked(bash("source .env.local; export -p"), cwd=self.bare)


class SecretsAllowed(GuardCase):
    """쓰는 것 — 메타데이터만 보거나 환경에 올리는 명령. 전부 실제로 막혔던 형태다."""

    def test_존재와_추적_여부_확인은_통과한다(self):
        self.assertPasses(bash(
            'ls -la .env.local 2>/dev/null && echo "--- 추적 여부 ---" && git ls-files .env.local '
            '&& echo "(추적됨!)" || echo "(git 에 없음)"; git check-ignore -v .env.local 2>/dev/null; '
            'echo "=== 히스토리에 있었나 ==="; git log --oneline --all -- .env.local | head -3'
        ), cwd=self.bare)
        self.assertPasses(bash("ls -la .env $H/.env ~/x/.env 2>/dev/null | awk '{print $NF, $5}'"), cwd=self.bare)
        self.assertPasses(bash("test -f .env.local && echo yes"), cwd=self.bare)
        self.assertPasses(bash("[ -s .env.local ] || echo empty"), cwd=self.bare)
        self.assertPasses(bash("stat -c %a .env.local; wc -l .env.local; chmod 600 .env.local"), cwd=self.bare)

    def test_변수로_존재만_확인하는_것은_통과한다(self):
        self.assertPasses(bash('for f in .env $H/.env; do [ -f $f ] && echo "$f 있음"; done'), cwd=self.bare)
        self.assertPasses(bash("f=.env.local; ls -la $f; test -s $f"), cwd=self.bare)

    def test_환경에_올려_쓰는_것은_통과한다(self):
        self.assertPasses(bash(
            'set -a; . ~/.env.local 2>/dev/null || . "$HOME/.env.local"; set +a; '
            'AIHUB_APIKEY="${AIHUBSHELL_API_KEY:-}" bash ~/aihub_data/fetch_samples.sh 2>&1 | grep -vE "^\\s*$" | tail -25'
        ), cwd=self.bare)
        self.assertPasses(bash("source .env.local && uv run pytest -q"), cwd=self.bare)
        self.assertPasses(bash("uv run --env-file .env.local pytest -q"), cwd=self.bare)
        self.assertPasses(bash("uv run --env-file=.env.local python scripts/run.py"), cwd=self.bare)
        self.assertPasses(bash("dotenv -f .env.local run -- pytest"), cwd=self.bare)
        self.assertPasses(bash("set -a; . .env.local; set +a; python -c 'import os; print(len(os.environ[\"K\"]))'"),
                          cwd=self.bare, msg="set +a 는 맨 set 이 아니다")

    def test_비밀값_파일을_찾는_검색은_통과한다(self):
        for cmd in (
            "git log --all --name-only | grep -iE '\\.env|\\.key|credential'",
            "grep -rn '\\.env\\.local' src/",
            "find . -name '.env*'",
            "rg credentials",
            # 파이프라인의 일부만 검색 명령이어도 그 segment 의 패턴은 패턴이다
            'git status --short | grep -v "^??"; git diff origin/main...HEAD --name-only '
            '| grep -E "assessment/data|\\.env|\\.key|credential"',
            "git diff origin/main...HEAD --name-only | grep -E 'assessment/data|\\.key$|credentials|secret' || echo ok",
            'grep -nE "ai-agent-dotfiles|local/\\.env|set -a" ~/.bashrc 2>/dev/null | head -5',
            'grep -n "def load_env_file" -A 25 src/backend.py | grep -n "Path\\|\\.env\\|environ" | head',
            'echo "데이터·비밀값 경로: $(git diff --name-only | grep -cE \'assessment/data|\\.env|\\.key\' || true)건"',
        ):
            self.assertPasses(bash(cmd), cwd=self.bare, msg=cmd)

    def test_echo_의_문구는_경로가_아니다(self):
        self.assertPasses(bash('echo "=== .env 류 ==="; ls -a . | grep -i env | head'), cwd=self.bare)
        self.assertPasses(bash("printf '%s\\n' 'copy .env.example to .env.local first'"), cwd=self.bare)

    def test_작은따옴표_속_마크다운_백틱은_치환이_아니다(self):
        # 이 세션에서 실제로 막힌 명령 — 문서의 `.credentials.json` 문구를 sed 로 고치던 중이었다
        self.assertPasses(bash("sed -i 's/· `.credentials*`/· 경로 모양의 `credentials` (`~\\/.aws\\/credentials`)/' docs/guard.md"), cwd=self.bare)
        self.assertPasses(bash("sed -i 's/old/see `.env.local` docs/' README.md"), cwd=self.bare)
        self.assertBlocked(bash("echo \"`cat .env.local`\""), cwd=self.bare, msg="큰따옴표 속 백틱은 치환이다")

    def test_큰따옴표_속_문구에_공백이_있으면_경로가_아니다(self):
        self.assertPasses(bash('gh pr create --title x --body "see .env.example and docs"'), cwd=self.bare)

    def test_jq_의_key_는_질의다(self):
        for cmd in (
            "jq -r .key out.json",
            "jq '.items[].key' out.json",
            "curl -s http://x | jq .key",
            "yq -r .key conf.yml",
        ):
            self.assertPasses(bash(cmd), cwd=self.bare, msg=cmd)

    def test_예시를_비밀값_파일로_복사하는_것은_보여주지_않는다(self):
        self.assertPasses(bash("cp .env.example .env.local"), cwd=self.bare)
        self.assertPasses(bash("cp .env.example .env"), cwd=self.bare)
        self.assertBlocked(bash("cp .env.local .env.backup"), cwd=self.bare, msg="원본이 비밀값이면 막는다")
        self.assertBlocked(bash("cp .env.local /tmp/"), cwd=self.bare)

    def test_실행기_래퍼_뒤의_안전_동사도_안전하다(self):
        self.assertPasses(bash("poetry run dotenv -f .env.local run pytest"), cwd=self.bare)
        self.assertPasses(bash("uv run dotenv -f .env.local run -- pytest"), cwd=self.bare)
        self.assertBlocked(bash("uv run python dump.py .env.local"), cwd=self.bare)

    def test_예시_파일은_비밀값이_아니다(self):
        self.assertPasses(bash("cat .env.example"), cwd=self.bare)
        self.assertPasses(tool("Read", ".env.example"), cwd=self.bare)
        self.assertPasses(tool("Write", ".env.sample"), cwd=self.bare)
        self.assertPasses(bash("cp .env.template .env.example"), cwd=self.bare)


class CodeAndProseBodies(GuardCase):
    """heredoc·`-c` 본문은 코드나 글이다. 그 안의 `.key` 속성과 `.env` 언급은 이름 검사에서 뺀다.
    실제로 막혔던 자리들 — 두더지잡기로 정규식을 세 번 고쳐도 새 모양이 계속 나왔다."""

    def test_python_heredoc_의_key_속성은_코드다(self):
        for body in (
            "n = int(ref.key)",
            "ks = [r.key for r in rs]",
            'print(f"{r.key!r}")',
            "seen[c.to_ref.raw]=c.to_ref.key\nfor c in cs: pass",
            "c = Counter(r.key\n  for r in rs)",
            'print(f"Bearer {self.key}")',
            "Cache.key(model, prompt, options)",
        ):
            self.assertPasses(bash(f"uv run python - <<'PY' 2>&1 | tail -22\n{body}\nPY"), cwd=self.bare, msg=body)
            self.assertPasses(bash(f"python3 -c '{body.splitlines()[0]}'"), cwd=self.bare, msg=body)

    def test_로더_스크립트를_heredoc_으로_쓰는_것은_통과한다(self):
        self.assertPasses(bash(
            "cat > $S/runwith.py <<'PY'\n"
            '"""키를 환경에만 올리고 하위 명령을 돌린다."""\n'
            "import os\nfrom pathlib import Path\n"
            'SRC = Path.home()/"nvidia_ai_course/course5--project/harness/.env.local"\n'
            "for line in SRC.read_text().splitlines():\n    k, v = line.split('=', 1)\n"
            "PY\npython3 $S/runwith.py pytest -q"
        ), cwd=self.bare)

    def test_문서에_env_를_적는_heredoc_은_통과한다(self):
        self.assertPasses(bash(
            "cat >> docs/worklog/2026-08-30.md <<'MD'\n\n- **`.env*` 를 git 이력에서 확인했다.**\nMD"
        ), cwd=self.bare)
        self.assertPasses(bash(
            "cat >> CLAUDE.md <<'EOF'\n- 키 미로드로 미실행(.env.local 이 보호 훅 차단 — 셸 env 주입 필요)\nEOF"
        ), cwd=self.bare)
        self.assertPasses(bash(
            "cat > .gitignore <<'IGN'\n.venv/\nexperiments/\n.env\n.env.*\nIGN\nsed -n '58,62p' pyproject.toml"
        ), cwd=self.bare, msg="heredoc 뒤에 이어지는 명령도 정상 판정")
        self.assertPasses(bash(
            "cat > /tmp/pr-body.md <<'MD'\n## 갈래별 판정\n| `.env` 처리 | ✅ |\nMD"
        ), cwd=self.bare)

    def test_heredoc_이_둘이어도_각각_뺀다(self):
        self.assertPasses(bash(
            "python3 - <<'PY'\nx = ref.key\nPY\ncat > .gitignore <<'IGN'\n.env\nIGN"
        ), cwd=self.bare)


class PassThrough(GuardCase):
    def test_판정_대상이_아니면_조용히_통과한다(self):
        self.assertPasses({"tool_name": "Glob", "tool_input": {"pattern": ".env*"}}, cwd=self.bare)
        self.assertPasses({"tool_name": "Bash", "tool_input": {}}, cwd=self.bare)

    def test_설정_타입이_틀려도_죽지_않는다(self):
        for cfg in ('{"protected_paths":["a/"],"allow_substrings":null}',
                    '{"protected_paths":["a/"],"allow_substrings":123}',
                    '{"protected_paths":"str"}',
                    '{"protected_paths":{"a":1}}'):
            d = pathlib.Path(self.tmp.name) / ("cfg" + str(abs(hash(cfg))))
            (d / ".claude").mkdir(parents=True, exist_ok=True)
            (d / ".claude" / "guard.json").write_text(cfg, encoding="utf-8")
            r = run(bash("git add x"), cwd=str(d))
            self.assertNotEqual(r.returncode, 1, f"크래시: {cfg}\n{r.stderr}")
            self.assertNotEqual(r.returncode, BLOCKED, f"엉뚱하게 막힘: {cfg}")

    def test_tool_input_이_dict_가_아니어도_죽지_않는다(self):
        for ti in (["a", "b"], "str", 3):
            r = run({"tool_name": "Bash", "tool_input": ti}, cwd=str(self.bare))
            self.assertEqual(r.returncode, 0, f"{ti}: {r.stderr}")

    def test_깨진_입력은_통과한다(self):
        r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, check=False)
        self.assertNotEqual(r.returncode, BLOCKED)

    def test_cwd_가_없어도_비밀값_규칙은_돈다(self):
        r = run(bash("cat .env.local"))
        self.assertEqual(r.returncode, BLOCKED)

    def test_우리_코드는_쓸_수_있다(self):
        self.assertPasses(tool("Write", "scripts/test-guard.py"))
        self.assertPasses(tool("Edit", "src/pipespec/adapters/llm/backend.py"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
