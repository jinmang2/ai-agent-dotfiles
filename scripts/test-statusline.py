#!/usr/bin/env python3
"""agent/statusline 테스트.  실행: python3 scripts/test-statusline.py

이 래퍼는 OMC HUD 를 그대로 부르되(에이전트·할 일·ralph·사용량·컨텍스트 전부 유지)
worktree 중복 표시 ` (wt:...)` 만 벗긴다. 여기서는 가짜 HUD 를 심어 래퍼만 시험한다 —
OMC 본체는 건드리지 않는다.
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
HOOK = REPO / "agent" / "statusline"
ESC = "\033"


class Statusline(unittest.TestCase):
    def run_with_hud(self, canned: str) -> str:
        """가짜 HUD 를 심어 래퍼를 돌린다. canned = OMC 가 냈다고 칠 출력."""
        with tempfile.TemporaryDirectory() as d:
            hud = pathlib.Path(d) / "hud"
            hud.mkdir()
            # omc-hud-cache.sh <mjs> — stdin 은 무시하고 canned 를 그대로 낸다
            (hud / "omc-hud-cache.sh").write_text(
                "#!/bin/sh\ncat <<'CANNED'\n" + canned + "\nCANNED\n", encoding="utf-8"
            )
            r = subprocess.run(
                [str(HOOK)], input="{}", capture_output=True, text=True,
                env={**os.environ, "CLAUDE_CONFIG_DIR": d}, check=False,
            )
            return r.stdout

    def test_worktree_중복_표시를_벗긴다(self):
        line = f"branch:feat/x {ESC}[2m(wt:x){ESC}[0m | profile:claude"
        out = self.run_with_hud(line)
        self.assertNotIn("(wt:", out)
        self.assertIn("branch:feat/x", out)
        self.assertIn("profile:claude", out)
        self.assertNotIn("  ", out, "wt 를 벗긴 자리에 두 칸 공백이 남으면 안 된다")

    def test_wt_가_없으면_그대로_통과시킨다(self):
        line = f"branch:main {ESC}[2m|{ESC}[0m ctx:72% | 5h:20%"
        out = self.run_with_hud(line)
        self.assertIn("ctx:72%", out)
        self.assertIn("5h:20%", out)

    def test_색_코드는_보존된다(self):
        line = f"branch:feat/x {ESC}[2m(wt:x){ESC}[0m | {ESC}[36mctx:72%{ESC}[0m"
        out = self.run_with_hud(line)
        self.assertIn(ESC, out, "ANSI 색이 통째로 지워지면 안 된다")
        self.assertIn("ctx:72%", out)

    def test_여러_줄도_각각_처리한다(self):
        canned = f"branch:feat/x (wt:x) | profile:claude\nctx:72% | 5h:20% | A:2"
        out = self.run_with_hud(canned)
        self.assertNotIn("(wt:", out)
        self.assertIn("A:2", out, "에이전트 표시 같은 아랫줄은 그대로 남아야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=1)
