#!/usr/bin/env python3
"""agent/window-label.sh 테스트.  실행: python3 scripts/test-window-label.py

별도 소켓에 tmux 서버를 하나 띄워 놓고 훅을 그 창에 대고 부른다. 실제 창은 건드리지 않는다.

여기서 못 박는 것: 임시 디렉토리에서 도는 **중첩 세션**의 이벤트는 무시한다.
pipespec 의 CLI 어댑터가 `tempfile.TemporaryDirectory()` 안에서 `claude -p` 를 돌리는데,
그 중첩 claude 도 훅을 부르므로 창 이름이 `tmpy2go8nt6` 가 되고 바깥 세션이 아직 도는데
✓ 가 찍혔다 (2026-09-05).
"""
import os
import pathlib
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
HOOK = REPO / "agent" / "window-label.sh"
SOCK = "agent-dotfiles-test"


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", "-L", SOCK, *args], capture_output=True, text=True, check=False).stdout.strip()


class WindowLabel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmux("kill-server")
        subprocess.run(["tmux", "-L", SOCK, "new-session", "-d", "-x", "80", "-y", "24",
                        "-c", str(REPO)], check=True)
        cls.pane = tmux("display", "-p", "#{pane_id}")
        socket = tmux("display", "-p", "#{socket_path}")
        cls.env = {
            **os.environ,
            "TMUX": f"{socket},0,0",  # 훅의 맨 `tmux` 가 이 서버를 보게 한다
            "TMUX_PANE": cls.pane,
            "AGENT_LABEL_LIB": str(REPO / "agent" / "label-of.sh"),
            "AGENT_PROFILES_CONF": str(REPO / "agent" / "profiles.conf"),
        }

    @classmethod
    def tearDownClass(cls):
        tmux("kill-server")
        cls.tmp.cleanup()

    def hook(self, state: str, cwd: str | None) -> None:
        payload = f'{{"cwd":"{cwd}","session_id":"x"}}' if cwd is not None else "{}"
        subprocess.run([str(HOOK), "", state], input=payload, env=self.env, capture_output=True,
                       text=True, check=False)

    def name(self) -> str:
        return tmux("display", "-p", "-t", self.pane, "#{window_name}")

    def cc(self) -> str:
        return tmux("show", "-w", "-t", self.pane, "-v", "@cc")

    def cc_sym(self) -> str:
        return tmux("show", "-w", "-t", self.pane, "-v", "@cc_sym")

    def cc_color(self) -> str:
        return tmux("show", "-w", "-t", self.pane, "-v", "@cc_color")

    def test_1_저장소_안이면_저장소_이름과_상태를_남긴다(self):
        self.hook("busy", str(REPO))
        self.assertEqual(self.name(), "ai-agent-dotfiles")
        self.assertEqual(self.cc(), "busy")

    def test_2_임시_디렉토리의_중첩_세션은_이름도_상태도_못_바꾼다(self):
        self.hook("busy", str(REPO))
        nested = tempfile.mkdtemp(prefix="tmp")  # /tmp/tmpXXXX — 실제로 존재하는 디렉토리
        try:
            self.hook("done", nested)
        finally:
            os.rmdir(nested)
        self.assertEqual(self.name(), "ai-agent-dotfiles", "임시 디렉토리 이름이 창 이름이 되면 안 된다")
        self.assertEqual(self.cc(), "busy", "중첩 실행의 Stop 이 바깥 세션의 상태를 덮으면 안 된다")

    def test_3_cwd_가_없으면_창의_경로로_이름을_짓는다(self):
        self.hook("busy", None)
        self.assertEqual(self.name(), "ai-agent-dotfiles")

    def test_5_임시_디렉토리에서_ccname_은_여전히_이름을_붙인다(self):
        # shell/agents.sh 의 ccname: @cc_label 을 심고 상태 없이 훅을 부른다
        tmux("set", "-w", "-t", self.pane, "@cc_label", "결제-마이그레이션")
        nested = tempfile.mkdtemp(prefix="tmp")
        try:
            self.hook("", nested)
            self.assertEqual(self.name(), "결제-마이그레이션")
        finally:
            os.rmdir(nested)
            tmux("set", "-w", "-t", self.pane, "-u", "@cc_label")
            self.hook("busy", str(REPO))

    def test_6_macOS_의_TMPDIR_는_끝에_슬래시가_붙어_와도_임시_루트다(self):
        self.hook("busy", str(REPO))
        # /tmp 밖에 두어야 /tmp/* 패턴이 아니라 TMPDIR 규칙이 시험된다
        root = pathlib.Path.home() / ".cache" / "agent-dotfiles-test" / "T"
        nested = root / "tmpabc"
        nested.mkdir(parents=True, exist_ok=True)
        try:
            env = {**self.env, "TMPDIR": str(root) + "/"}
            subprocess.run([str(HOOK), "", "done"], input=f'{{"cwd":"{nested}"}}', env=env,
                           capture_output=True, text=True, check=False)
            self.assertEqual(self.cc(), "busy", "TMPDIR 끝의 슬래시 때문에 중첩 세션을 놓치면 안 된다")
            env.pop("TMPDIR")
            mac = pathlib.Path.home() / ".cache" / "agent-dotfiles-test" / "var" / "folders" / "qr" / "T" / "tmpx"
            mac.mkdir(parents=True, exist_ok=True)
            payload = '{"cwd":"/private/var/folders/qr/T/tmpx"}'  # macOS 가 TMPDIR 없이 주는 모양
            subprocess.run([str(HOOK), "", "done"], input=payload, env=env,
                           capture_output=True, text=True, check=False)
            self.assertEqual(self.cc(), "busy", "/private/var/folders 도 임시 루트다")
        finally:
            import shutil
            shutil.rmtree(pathlib.Path.home() / ".cache" / "agent-dotfiles-test", ignore_errors=True)

    def test_7_cwd_가_뒤에_또_나와도_맨_앞_것을_쓴다(self):
        nested = tempfile.mkdtemp(prefix="tmp")
        try:
            payload = f'{{"cwd":"{nested}","tool_response":{{"cwd":"{REPO}"}}}}'
            subprocess.run([str(HOOK), "", "done"], input=payload, env=self.env,
                           capture_output=True, text=True, check=False)
        finally:
            os.rmdir(nested)
        self.assertEqual(self.cc(), "busy", "뒤에 나온 cwd 가 앞의 것을 덮으면 임시 판정이 뚫린다")

    def test_8_상태가_같아도_상태줄_필드는_복구한다(self):
        self.hook("busy", str(REPO))
        tmux("set", "-w", "-t", self.pane, "-u", "@cc_sym")
        tmux("set", "-w", "-t", self.pane, "-u", "@cc_color")
        self.hook("busy", str(REPO))
        self.assertIn("»", self.cc_sym(), "상태가 같아도 상태줄 기호는 복구되어야 한다")
        self.assertEqual(self.cc_color(), "bg=colour208,fg=colour235")

    def test_4_세션이_끝나면_done_이_남는다(self):
        self.hook("busy", str(REPO))
        self.hook("done", str(REPO))
        self.assertEqual(self.cc(), "done")


if __name__ == "__main__":
    unittest.main(verbosity=1)
