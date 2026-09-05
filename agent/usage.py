#!/usr/bin/env python3
"""claude 사용량·비용·캐시 집계 — ~/.claude/projects/**/*.jsonl 를 훑는다.

transcript 에는 토큰만 있고 달러가 없다(costUSD 부재, 실측 확인). 그래서 토큰×단가로
**계산**한다 — 정확한 청구서가 아니라 추정이다. 단가표(PRICES)는 근사이고 고쳐도 된다.

세 명령: `cache`(캐시 낭비)·`projects`(프로젝트별 비용)·`daily`(일별 비용). 남들(ccusage 등)이 비용은 잘 세도 캐시 효율은
거의 안 보여준다 — 여기가 차별점이다.

단가 근거 (claude-api 스킬, 2026-06 기준):
  입력/출력 per MTok: fable-5-1 10/50 · opus-5·4-8 5/25 · sonnet-5 2/10 · haiku-4-5 1/5
  캐시: 쓰기 5분 = 입력×1.25, 쓰기 1시간 = 입력×2, 읽기 = 입력×0.1
        단 Fable 5/5.1 은 읽기 $0.25/MTok 로 문서에 특별 명시(0.1×=$1.00 아님).
시험: scripts/test-usage.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import namedtuple
from pathlib import Path

Rec = namedtuple("Rec", "project rid model usage date")

M = 1_000_000

# per MTok. cr = 캐시읽기, cw5m = 5분 캐시쓰기, cw1h = 1시간 캐시쓰기.
PRICES = {
    "claude-fable-5-1": {"in": 10, "out": 50, "cr": 0.25, "cw5m": 12.5, "cw1h": 20},
    "claude-fable-5":   {"in": 10, "out": 50, "cr": 0.25, "cw5m": 12.5, "cw1h": 20},
    "claude-opus-5":    {"in": 5,  "out": 25, "cr": 0.5,  "cw5m": 6.25, "cw1h": 10},
    "claude-opus-4-8":  {"in": 5,  "out": 25, "cr": 0.5,  "cw5m": 6.25, "cw1h": 10},
    "claude-sonnet-5":  {"in": 2,  "out": 10, "cr": 0.2,  "cw5m": 2.5,  "cw1h": 4},
    "claude-haiku-4-5": {"in": 1,  "out": 5,  "cr": 0.1,  "cw5m": 1.25, "cw1h": 2},
}


def _split_cw(usage: dict) -> tuple[int, int]:
    """캐시생성을 1시간·5분으로 나눈다. 세부가 없으면 전부 5분으로 본다(보수적)."""
    cc = usage.get("cache_creation") or {}
    h = cc.get("ephemeral_1h_input_tokens")
    m = cc.get("ephemeral_5m_input_tokens")
    if h is None and m is None:
        return 0, usage.get("cache_creation_input_tokens", 0)
    return h or 0, m or 0


def cost_of(model: str, usage: dict) -> dict:
    """이 턴의 비용 분해 (달러). 모르는 모델·synthetic 은 0."""
    p = PRICES.get(model)
    if not p:
        return {"in": 0.0, "out": 0.0, "cw": 0.0, "cr": 0.0, "total": 0.0}
    cw1h, cw5m = _split_cw(usage)
    c = {
        "in": usage.get("input_tokens", 0) / M * p["in"],
        "out": usage.get("output_tokens", 0) / M * p["out"],
        "cw": (cw1h / M * p["cw1h"]) + (cw5m / M * p["cw5m"]),
        "cr": usage.get("cache_read_input_tokens", 0) / M * p["cr"],
    }
    c["total"] = c["in"] + c["out"] + c["cw"] + c["cr"]
    return c


def counterfactual_cost(model: str, usage: dict) -> float:
    """캐시가 없었다면 — 입력측 토큰(생입력+캐시읽기+캐시쓰기)을 전부 생입력 단가로."""
    p = PRICES.get(model)
    if not p:
        return 0.0
    cw1h, cw5m = _split_cw(usage)
    input_side = (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                  + cw1h + cw5m)
    return input_side / M * p["in"] + usage.get("output_tokens", 0) / M * p["out"]


def _blank() -> dict:
    return {"tok": {"in": 0, "out": 0, "cr": 0, "cw1h": 0, "cw5m": 0},
            "cost": {"in": 0.0, "out": 0.0, "cw": 0.0, "cr": 0.0, "total": 0.0},
            "counterfactual": 0.0, "turns": 0}


def aggregate(records, key=lambda r: r.project) -> dict:
    """Rec 목록을 key(r) 로 묶는다.  requestId 로 중복 제거하되 마지막 것을 쓴다
    (스트리밍 중간 항목 제거).  key 를 바꾸면 프로젝트별·날짜별 등 축을 고를 수 있다."""
    seen: dict = {}  # requestId → 마지막 Rec
    order: list = []
    for rec in records:
        k = rec.rid if rec.rid else id(rec)
        if k not in seen:
            order.append(k)
        seen[k] = rec
    agg: dict[str, dict] = {}
    for k in order:
        rec = seen[k]
        model, usage = rec.model, rec.usage
        a = agg.setdefault(key(rec), _blank())
        a["turns"] += 1
        cw1h, cw5m = _split_cw(usage)
        a["tok"]["in"] += usage.get("input_tokens", 0)
        a["tok"]["out"] += usage.get("output_tokens", 0)
        a["tok"]["cr"] += usage.get("cache_read_input_tokens", 0)
        a["tok"]["cw1h"] += cw1h
        a["tok"]["cw5m"] += cw5m
        c = cost_of(model, usage)
        for k in ("in", "out", "cw", "cr", "total"):
            a["cost"][k] += c[k]
        a["counterfactual"] += counterfactual_cost(model, usage)
    return agg


def hit_ratio(a: dict) -> float:
    """캐시읽기 / (읽기 + 생성 + 생입력). 생성을 분모에 넣어 절약을 부풀리지 않는다."""
    t = a["tok"]
    denom = t["cr"] + t["cw1h"] + t["cw5m"] + t["in"]
    return t["cr"] / denom if denom else 0.0


def savings(a: dict) -> float:
    """캐시가 아꼈거나(양수) 오히려 더 든(음수) 달러 = 반사실 - 실제."""
    return a["counterfactual"] - a["cost"]["total"]


# ── 스캔 ────────────────────────────────────────────────────────────────────

_HOME_PREFIX = re.compile(r"^-(?:home|Users)-[^-]+-")


def _project_dir(jsonl_path: Path) -> Path:
    """파일이 속한 프로젝트 디렉토리 = `projects/` 바로 아래 폴더.  서브에이전트 기록은
    `<project>/subagents/*.jsonl` 로 한 단계 더 들어가 있어서, 바로 위 폴더를 쓰면 모든
    프로젝트의 서브에이전트가 `subagents` 하나로 뭉친다(실측 버그).  parent 가 projects
    인 조상을 찾아 그걸 쓴다."""
    for parent in jsonl_path.parents:
        if parent.parent.name == "projects":
            return parent
    return jsonl_path.parent


def _project_name(project_dir: Path) -> str:
    """디렉토리 이름은 cwd 를 `/`→`-` 로 바꾼 것.  홈 접두사(-home-<user>-)만 벗긴다 —
    마지막 조각만 쓰면 agentic-memory 가 memory 로 뭉개진다."""
    d = project_dir.name
    return _HOME_PREFIX.sub("", d) or d.lstrip("-") or d


def scan(roots):
    """각 root 아래 *.jsonl 을 훑어 (project, requestId, model, usage) 를 yield."""
    for root in roots:
        root = Path(root)
        files = [root] if root.suffix == ".jsonl" else sorted(root.rglob("*.jsonl"))
        for f in files:
            proj = _project_name(_project_dir(f))
            try:
                fh = f.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:  # noqa: BLE001,S112
                        continue
                    msg = d.get("message") or {}
                    if msg.get("role") != "assistant":
                        continue
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    date = (d.get("timestamp") or "")[:10]  # YYYY-MM-DD
                    yield Rec(proj, d.get("requestId") or msg.get("id"), msg.get("model", ""), usage, date)


# ── 리포트 ──────────────────────────────────────────────────────────────────

def _k(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.0f}M"
    if n >= 1000:
        return f"{n//1000}k"
    return str(n)


W = 30  # 프로젝트 이름 칸


def _row(name, a):
    return (f"{name[:W]:<{W}}{'$'+format(a['cost']['total'],'.2f'):>10}{hit_ratio(a)*100:>5.0f}%"
            f"{'$'+format(a['cost']['cw'],'.0f'):>8}{'$'+format(a['cost']['cr'],'.0f'):>7}"
            f"{'$'+format(savings(a),'.0f'):>9}{_k(a['tok']['cw1h']):>8}")


def _cost_row(name, a, w):
    return (f"{name[:w]:<{w}}{'$'+format(a['cost']['total'],'.2f'):>10}"
            f"{_k(a['tok']['in']):>8}{_k(a['tok']['out']):>9}"
            f"{_k(a['tok']['cr']):>10}{_k(a['tok']['cw1h']+a['tok']['cw5m']):>10}{a['turns']:>7}")


def cost_report(agg: dict, label: str, top: int | None = None) -> str:
    """비용 중심 표 (daily·projects 공용).  label = 첫 칸 제목."""
    rows = sorted(agg.items(), key=lambda kv: kv[1]["cost"]["total"], reverse=True)
    if label == "date":  # 날짜는 시간순이 자연스럽다
        rows = sorted(agg.items())
    w = 16
    out = [f"{label:<{w}}{'cost':>10}{'in':>8}{'out':>9}{'cache-rd':>10}{'cache-wr':>10}{'turns':>7}",
           "─" * (w + 54)]
    shown = rows[-top:] if (top and label == "date") else (rows[:top] if top else rows)
    tot = _blank()
    for _n, a in rows:
        for k in tot["tok"]:
            tot["tok"][k] += a["tok"][k]
        for k in tot["cost"]:
            tot["cost"][k] += a["cost"][k]
    for name, a in shown:
        out.append(_cost_row(name, a, w))
    out.append("─" * (w + 49))
    out.append(_cost_row(f"합계 {len(rows)}", tot, w))
    out.append("")
    out.append("단가는 추정 — 정확한 청구서 아님 (agent/usage.py 의 PRICES). 캐시 낭비는 agent-usage cache.")
    return "\n".join(out)


def cache_report(agg: dict, top: int | None = None) -> str:
    rows = sorted(agg.items(), key=lambda kv: kv[1]["cost"]["total"], reverse=True)
    shown = rows[:top] if top else rows
    out = [f"{'project':<{W}}{'cost':>10}{'hit':>6}{'write$':>8}{'read$':>7}{'saved$':>9}{'1h-wr':>8}",
           "─" * (W + 48)]
    tot = _blank(); tot["counterfactual"] = 0.0
    for proj, a in rows:  # 합계는 전체 기준
        for k in tot["tok"]:
            tot["tok"][k] += a["tok"][k]
        for k in tot["cost"]:
            tot["cost"][k] += a["cost"][k]
        tot["counterfactual"] += a["counterfactual"]
    for proj, a in shown:
        out.append(_row(proj, a))
    if top and len(rows) > top:
        out.append(f"… 그 외 {len(rows)-top}개 프로젝트")
    out.append("─" * (W + 48))
    out.append(_row(f"합계 {len(rows)}개", tot))
    out.append("")
    out.append(f"캐시가 아꼈다: 실제 ${tot['cost']['total']:.0f} vs 캐시 없었다면 "
               f"${tot['counterfactual']:.0f} → ${savings(tot):+.0f}")
    out.append("hit = 캐시읽기/(읽기+생성+생입력), 생성을 분모에 넣어 절약을 부풀리지 않음.")
    out.append("saved$ = 캐시 없이 전부 생입력이었을 때 대비 아낀 돈(음수면 캐시가 오히려 손해).")
    out.append("단가는 추정 — 정확한 청구서 아님. 고치려면 agent/usage.py 의 PRICES.")
    return "\n".join(out)


def main(argv) -> int:
    cmd = argv[0] if argv else "cache"
    if cmd not in ("cache", "daily", "projects"):
        print(f"알 수 없는 명령: {cmd}  (cache · daily · projects)", file=sys.stderr)
        return 2
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    if not root.is_dir():
        print(f"{root} 없음", file=sys.stderr)
        return 1
    recs = list(scan([root]))
    if cmd == "cache":
        print(cache_report(aggregate(recs), top=25))
    elif cmd == "projects":
        print(cost_report(aggregate(recs), "project", top=25))
    elif cmd == "daily":
        print(cost_report(aggregate(recs, key=lambda r: r.date or "?"), "date", top=30))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
