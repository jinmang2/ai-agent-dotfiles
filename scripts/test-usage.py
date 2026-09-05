#!/usr/bin/env python3
"""agent/usage.py 테스트.  실행: python3 scripts/test-usage.py

transcript(~/.claude/projects/**/*.jsonl)의 턴별 usage 를 토큰×단가로 집계한다.
transcript 엔 달러가 없어서(costUSD 부재) 반드시 계산해야 한다.  단가표는 근사이고
사람이 고칠 수 있다 — "정확한 청구서가 아니라 추정".

핵심 판단(리서치 근거):
  · 캐시생성 1시간 = 입력의 2×, 5분 = 1.25×, 캐시읽기 = 0.1× (단, Fable 은 $0.25/MTok 명시)
  · requestId 로 중복 제거(스트리밍 중간 항목은 마지막만)
  · 캐시 적중률의 분모에 캐시생성을 넣는다 — 쓰기 단가로 과금되니 절약을 부풀리지 않으려고
"""
import importlib.util
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location(
    "usage", pathlib.Path(__file__).resolve().parents[1] / "agent" / "usage.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)

M = 1_000_000


def usage(**kw):
    """usage 딕셔너리 헬퍼. 토큰 단위."""
    cc = {"ephemeral_1h_input_tokens": kw.pop("cw1h", 0),
          "ephemeral_5m_input_tokens": kw.pop("cw5m", 0)}
    return {"input_tokens": kw.pop("in_", 0), "output_tokens": kw.pop("out", 0),
            "cache_read_input_tokens": kw.pop("cr", 0),
            "cache_creation_input_tokens": cc["ephemeral_1h_input_tokens"] + cc["ephemeral_5m_input_tokens"],
            "cache_creation": cc}


class Pricing(unittest.TestCase):
    def test_기본_입출력_단가(self):
        cost = u.cost_of("claude-fable-5-1", usage(in_=M, out=M))
        self.assertAlmostEqual(cost["in"], 10.0, places=4)
        self.assertAlmostEqual(cost["out"], 50.0, places=4)

    def test_fable_캐시읽기는_특별단가_025(self):
        cost = u.cost_of("claude-fable-5-1", usage(cr=M))
        self.assertAlmostEqual(cost["cr"], 0.25, places=4)  # 0.1× 아님

    def test_1시간_캐시쓰기는_입력의_2배(self):
        cost = u.cost_of("claude-fable-5-1", usage(cw1h=M))
        self.assertAlmostEqual(cost["cw"], 20.0, places=4)  # 10 × 2

    def test_5분_캐시쓰기는_입력의_125배(self):
        cost = u.cost_of("claude-opus-5", usage(cw5m=M))
        self.assertAlmostEqual(cost["cw"], 6.25, places=4)  # 5 × 1.25

    def test_opus_캐시읽기는_표준_01배(self):
        cost = u.cost_of("claude-opus-5", usage(cr=M))
        self.assertAlmostEqual(cost["cr"], 0.5, places=4)  # 5 × 0.1

    def test_모르는_모델은_0_이되_죽지_않는다(self):
        cost = u.cost_of("claude-unknown-9", usage(in_=M))
        self.assertEqual(cost["total"], 0.0)

    def test_synthetic_은_0(self):
        self.assertEqual(u.cost_of("<synthetic>", usage(in_=M))["total"], 0.0)


class Counterfactual(unittest.TestCase):
    def test_캐시_없었다면_모든_입력측_토큰이_생입력_단가(self):
        # 읽기 1M + 생성 1M 을 전부 생입력으로 치면 Fable 은 (1M+1M)×$10 = $20
        cf = u.counterfactual_cost("claude-fable-5-1", usage(cr=M, cw1h=M, out=M))
        self.assertAlmostEqual(cf, 20.0 + 50.0, places=4)  # 입력측 $20 + 출력 $50


class Aggregate(unittest.TestCase):
    def test_requestId_로_중복제거_마지막만(self):
        recs = [
            ("proj", "r1", "claude-fable-5-1", usage(out=1000)),   # 스트리밍 중간
            ("proj", "r1", "claude-fable-5-1", usage(out=5000)),   # 최종 — 이것만
            ("proj", "r2", "claude-fable-5-1", usage(out=2000)),
        ]
        agg = u.aggregate(recs)
        self.assertEqual(agg["proj"]["tok"]["out"], 7000)  # 5000 + 2000, 1000 제외

    def test_프로젝트별로_나뉜다(self):
        recs = [("a", "r1", "claude-fable-5-1", usage(cr=M)),
                ("b", "r2", "claude-fable-5-1", usage(cr=M))]
        agg = u.aggregate(recs)
        self.assertEqual(set(agg), {"a", "b"})

    def test_적중률은_생성을_분모에_넣는다(self):
        # read=90, creation=9, fresh=1 → 90/(90+9+1)=0.9
        recs = [("p", "r1", "claude-fable-5-1", usage(cr=90, cw1h=9, in_=1))]
        agg = u.aggregate(recs)
        self.assertAlmostEqual(u.hit_ratio(agg["p"]), 0.9, places=4)

    def test_절약은_반사실_빼기_실제(self):
        recs = [("p", "r1", "claude-fable-5-1", usage(cr=M))]  # 실제 $0.25, 반사실 $10
        agg = u.aggregate(recs)
        self.assertAlmostEqual(u.savings(agg["p"]), 10.0 - 0.25, places=3)


class Scan(unittest.TestCase):
    def test_jsonl_에서_assistant_usage_만_뽑는다(self):
        import json, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            proj = pathlib.Path(d) / "projects" / "-home-x-myrepo"
            proj.mkdir(parents=True)
            f = proj / "s.jsonl"
            f.write_text("\n".join([
                json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
                json.dumps({"requestId": "r1", "message": {"role": "assistant",
                            "model": "claude-fable-5-1", "usage": usage(out=100)}}),
                "not json",
            ]), encoding="utf-8")
            # 서브에이전트 기록은 <project>/subagents/ 아래 — 부모 프로젝트로 귀속돼야
            sub = proj / "subagents"; sub.mkdir()
            (sub / "a.jsonl").write_text(json.dumps({"requestId": "r2",
                "message": {"role": "assistant", "model": "claude-fable-5-1", "usage": usage(out=50)}}), encoding="utf-8")
            recs = list(u.scan([pathlib.Path(d) / "projects"]))
            self.assertEqual(len(recs), 2)
            self.assertEqual({r[0] for r in recs}, {"myrepo"}, "서브에이전트도 myrepo 로")


if __name__ == "__main__":
    unittest.main(verbosity=1)
