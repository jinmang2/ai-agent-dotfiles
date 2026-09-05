#!/usr/bin/env python3
"""agent/hud-cacheline.py 테스트.  실행: python3 scripts/test-hud-cacheline.py

상태줄 셋째 줄 — 프롬프트 캐시 남은 수명 + 세션 비용.  Claude Code 가 stdin 으로 주는
`prompt_cache.expires_at`·`ttl` 과 `cost.total_cost_usd` 를 읽는다.  캐시 타이머는 유휴
중에 상태줄이 다시 그려지며 `expires_at - now` 로 줄어든다.
"""
import json
import re
import subprocess
import sys
import time
import pathlib
import unittest

HOOK = pathlib.Path(__file__).resolve().parents[1] / "agent" / "hud-cacheline.py"


def run(payload: dict) -> str:
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, check=False)
    return r.stdout


def plain(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s).strip()


class CacheLine(unittest.TestCase):
    def test_남은_수명과_비용을_낸다(self):
        now = int(time.time())
        out = plain(run({"prompt_cache": {"ttl": "1h", "expires_at": now + 59 * 60,
                                          "caching_observed": True},
                        "cost": {"total_cost_usd": 166.09}}))
        self.assertRegex(out, r"cache 5[0-9]m")
        self.assertIn("$166", out)

    def test_유휴로_줄어든다(self):
        now = int(time.time())
        five = plain(run({"prompt_cache": {"ttl": "1h", "expires_at": now + 5 * 60,
                                           "caching_observed": True}}))
        self.assertRegex(five, r"cache [45]m")

    def test_만료되면_cold(self):
        now = int(time.time())
        out = plain(run({"prompt_cache": {"ttl": "1h", "expires_at": now - 100,
                                          "caching_observed": True}}))
        self.assertIn("cold", out)
        self.assertNotIn("-", out, "음수 분을 그대로 내면 안 된다")

    def test_임박하면_빨강(self):
        now = int(time.time())
        raw = run({"prompt_cache": {"ttl": "1h", "expires_at": now + 2 * 60,
                                    "caching_observed": True}})
        self.assertIn("203", raw, "3분 미만이면 빨강(203)")

    def test_넉넉하면_초록(self):
        now = int(time.time())
        raw = run({"prompt_cache": {"ttl": "1h", "expires_at": now + 40 * 60,
                                    "caching_observed": True}})
        self.assertIn("114", raw, "넉넉하면 초록(114)")

    def test_캐시_정보가_없으면_캐시_필드를_뺀다(self):
        out = plain(run({"cost": {"total_cost_usd": 3.2}}))
        self.assertNotIn("cache", out)
        self.assertIn("$3", out)

    def test_비용이_작으면_소수로(self):
        out = plain(run({"cost": {"total_cost_usd": 2.34}}))
        self.assertIn("$2.3", out)

    def test_아무것도_없으면_빈_출력(self):
        self.assertEqual(plain(run({})), "")
        self.assertEqual(plain(run({"prompt_cache": {"caching_observed": False}})), "")

    def test_깨진_입력은_조용히_빈_출력(self):
        r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                          capture_output=True, text=True, check=False)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(plain(r.stdout), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
