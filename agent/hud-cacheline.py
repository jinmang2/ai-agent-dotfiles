#!/usr/bin/env python3
"""상태줄 셋째 줄 — 프롬프트 캐시 남은 수명 + 세션 비용.  agent/statusline 이 붙인다.

Claude Code 가 상태줄 stdin 으로 주는 것에서만 읽는다:
  prompt_cache.hit_ratio · caching_observed  → 캐시가 얼마나 잘 맞나(효율)
  cost.total_cost_usd                        → 세션 누적 비용

**왜 적중률인가 (만료 타이머가 아니라):**  만료까지 남은 시간(expires_at - now)은 매
요청이 캐시를 1시간으로 갱신하기 때문에, 활동 중 상태줄을 볼 때 늘 ~59m 로 고정돼 보인다
(유휴 재렌더 때만 줄지만 그때는 안 본다).  그래서 무의미하다.  대신 세션 캐시 적중률을
낸다 — 세션마다 다르고, 낮으면 재읽기에 헛돈을 쓰는 중이라는 실제 신호다.  프로젝트별
캐시 낭비 상세는 `agent-usage cache`.

색: 적중률 90%↑ 초록 · 70%↑ 노랑 · 그 아래 빨강.  값이 없는 필드는 뺀다.  둘 다 없으면
아무것도 내지 않는다(빈 줄이 생기지 않게).
"""
from __future__ import annotations

import json
import sys

R = "\033[0m"
GREEN, YELLOW, RED, DIM = "38;5;114", "38;5;214", "38;5;203", "38;5;245"


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}{R}"


def cache_field(pc: dict) -> str | None:
    """캐시 적중률.  만료 카운트다운(expires_at)은 활동 사용자에겐 늘 ~59m 로 고정이라
    (매 요청이 캐시를 갱신) 쓸모없다 — 세션마다 다르고 의미 있는 적중률을 낸다.
    낮으면 재읽기에 헛돈을 쓰는 중.  어떤 세션은 hit_ratio 를 안 채우니, 없으면 뺀다."""
    if not pc.get("caching_observed"):
        return None
    hr = pc.get("hit_ratio")
    if not isinstance(hr, (int, float)):
        return None
    pct = hr * 100
    color = GREEN if pct >= 90 else YELLOW if pct >= 70 else RED
    return f"{c(DIM, 'cache')} {c(color, f'{pct:.0f}%')}"


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
