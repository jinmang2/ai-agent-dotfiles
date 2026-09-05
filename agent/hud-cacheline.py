#!/usr/bin/env python3
"""상태줄 셋째 줄 — 프롬프트 캐시 남은 수명 + 세션 비용.  agent/statusline 이 붙인다.

Claude Code 가 상태줄 stdin 으로 주는 것에서만 읽는다:
  prompt_cache.expires_at · ttl · caching_observed  → 워밍된 캐시가 언제 식나
  cost.total_cost_usd                               → 세션 누적 비용

**캐시 타이머가 유휴 중에 줄어드는 이유:**  Claude Code 는 유휴에도 상태줄을 주기적으로
다시 그리는데, 그동안 `expires_at` 은 마지막 요청 시각(+1h)에 고정된 채 현재 시각만
흘러간다.  그래서 `expires_at - now` 가 59m → … → 0 으로 줄어든다.  0(cold)이 되면 다음
메시지가 컨텍스트를 통째로 다시 읽는다(prompt_cache.recache_tokens_if_cold, 수십만 토큰).
곧 자리를 비우거나 /compact 할 거면 이게 낮을 때 하면 추가 비용이 없다.

색: 넉넉(초록) · 임박(노랑) · 3분 미만/만료(빨강).  값이 없는 필드는 뺀다.  둘 다 없으면
아무것도 내지 않는다(빈 줄이 생기지 않게).
"""
from __future__ import annotations

import json
import sys
import time

R = "\033[0m"
GREEN, YELLOW, RED, DIM = "38;5;114", "38;5;214", "38;5;203", "38;5;245"


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}{R}"


def cache_field(pc: dict) -> str | None:
    if not pc.get("caching_observed"):
        return None
    exp = pc.get("expires_at")
    if not isinstance(exp, (int, float)):
        return None
    left = int(exp) - int(time.time())
    if left <= 0:
        return c(RED, "cache cold")
    mins = left // 60
    color = GREEN if mins >= 15 else YELLOW if mins >= 3 else RED
    return f"{c(DIM, 'cache')} {c(color, f'{mins}m')}"


def cost_field(cost: dict) -> str | None:
    usd = cost.get("total_cost_usd")
    if not isinstance(usd, (int, float)):
        return None
    return c(DIM, f"${usd:.0f}" if usd >= 10 else f"${usd:.2f}")


def main() -> int:
    try:
        d = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 — 못 읽으면 조용히 빈 줄
        return 0
    if not isinstance(d, dict):
        return 0
    parts = [f for f in (cache_field(d.get("prompt_cache") or {}),
                         cost_field(d.get("cost") or {})) if f]
    if parts:
        print(c(DIM, " · ").join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
