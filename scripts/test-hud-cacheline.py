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
    def test_적중률과_비용을_낸다(self):
        # 만료 카운트다운은 활동 사용자에겐 늘 ~59m 로 고정이라 무의미하다.
        # 대신 세션마다 다르고 의미 있는 캐시 적중률을 낸다.
        out = plain(run({"prompt_cache": {"caching_observed": True, "hit_ratio": 0.97},
                        "cost": {"total_cost_usd": 166.09}}))
        self.assertIn("cache 97%", out)
        self.assertIn("$166", out)

    def test_적중률_낮으면_빨강(self):
        raw = run({"prompt_cache": {"caching_observed": True, "hit_ratio": 0.4}})
        self.assertIn("203", raw, "70% 미만이면 빨강(203)")
        self.assertIn("cache 40%", plain(raw))

    def test_적중률_높으면_초록(self):
        raw = run({"prompt_cache": {"caching_observed": True, "hit_ratio": 0.97}})
        self.assertIn("114", raw, "90% 이상이면 초록(114)")

    def test_적중률이_없으면_캐시_필드를_뺀다(self):
        # 어떤 세션은 hit_ratio 를 안 채운다 — 그때는 0% 로 오해시키지 말고 뺀다
        out = plain(run({"prompt_cache": {"caching_observed": True}, "cost": {"total_cost_usd": 3.2}}))
        self.assertNotIn("cache", out)
        self.assertIn("$3", out)

    def test_캐시_관측_안됐으면_뺀다(self):
        out = plain(run({"prompt_cache": {"caching_observed": False, "hit_ratio": 0.9},
                        "cost": {"total_cost_usd": 3.2}}))
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
