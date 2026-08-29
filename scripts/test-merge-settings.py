#!/usr/bin/env python3
"""merge-settings.py 테스트.  실행: python3 scripts/test-merge-settings.py

설정 병합은 조용히 틀리면 알아채기 어렵다 — 권한 한 줄이 사라져도 다음에
승인 프롬프트가 뜰 때까지 모른다. 그래서 규칙마다 테스트를 둔다.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "merge-settings.py"

spec = importlib.util.spec_from_file_location("merge_settings", SCRIPT)
ms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ms)


class Merge(unittest.TestCase):
    def test_객체는_깊게_병합된다(self):
        self.assertEqual(
            ms.merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3, "d": 4}}),
            {"a": {"b": 1, "c": 3, "d": 4}},
        )

    def test_스칼라는_오버레이가_이긴다(self):
        self.assertEqual(ms.merge({"model": "opus"}, {"model": "sonnet"}), {"model": "sonnet"})

    def test_배열은_이어붙고_중복이_제거된다(self):
        self.assertEqual(ms.merge({"a": [1, 2]}, {"a": [2, 3]}), {"a": [1, 2, 3]})

    def test_객체가_든_배열도_중복이_제거된다(self):
        base = [{"x": 1}, {"y": 2}]
        over = [{"y": 2}, {"z": 3}]
        self.assertEqual(ms.merge(base, over), [{"x": 1}, {"y": 2}, {"z": 3}])

    def test_배열_순서는_공용이_먼저다(self):
        self.assertEqual(ms.merge({"a": ["b", "a"]}, {"a": ["c"]}), {"a": ["b", "a", "c"]})

    def test_null_은_키를_삭제한다(self):
        self.assertEqual(ms.merge({"a": 1, "b": 2}, {"b": None}), {"a": 1})

    def test_없는_키를_null_로_지워도_괜찮다(self):
        self.assertEqual(ms.merge({"a": 1}, {"zzz": None}), {"a": 1})

    def test_타입이_다르면_오버레이가_이긴다(self):
        self.assertEqual(ms.merge({"a": {"b": 1}}, {"a": "문자열"}), {"a": "문자열"})

    def test_공용은_변형되지_않는다(self):
        base = {"a": {"b": 1}}
        ms.merge(base, {"a": {"b": 2}})
        self.assertEqual(base, {"a": {"b": 1}})


class Render(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())

    def write(self, name, obj):
        p = self.dir / name
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def test_comment_는_결과에_안_들어간다(self):
        b = self.write("b.json", {"a": 1})
        o = self.write("o.json", {"_comment": ["설명"], "b": 2})
        self.assertEqual(json.loads(ms.render(b, o)), {"a": 1, "b": 2})

    def test_멱등하다(self):
        b = self.write("b.json", {"p": {"allow": ["x"]}})
        o = self.write("o.json", {"p": {"allow": ["y"]}})
        first = ms.render(b, o)
        self.assertEqual(first, ms.render(b, o))
        self.assertEqual(json.loads(first)["p"]["allow"], ["x", "y"])

    def test_한글이_이스케이프되지_않는다(self):
        b = self.write("b.json", {"a": "한글"})
        o = self.write("o.json", {})
        self.assertIn("한글", ms.render(b, o))

    def test_줄바꿈으로_끝난다(self):
        b = self.write("b.json", {"a": 1})
        o = self.write("o.json", {})
        self.assertTrue(ms.render(b, o).endswith("\n"))


class Diff(unittest.TestCase):
    def test_사라지는_항목을_보여준다(self):
        lines = ms.diff_report({"p": {"allow": ["x", "손으로넣은것"]}}, {"p": {"allow": ["x"]}})
        self.assertTrue(any("손으로넣은것" in l and "-" in l for l in lines))

    def test_추가_삭제_변경을_구분한다(self):
        lines = "\n".join(ms.diff_report({"a": 1, "b": 2}, {"a": 9, "c": 3}))
        self.assertIn("변경  a", lines)
        self.assertIn("삭제  b", lines)
        self.assertIn("추가  c", lines)

    def test_같으면_아무것도_안_나온다(self):
        self.assertEqual(ms.diff_report({"a": 1}, {"a": 1}), [])


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.b = self.dir / "b.json"
        self.o = self.dir / "o.json"
        self.b.write_text('{"a": 1}', encoding="utf-8")
        self.o.write_text('{"b": 2}', encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True, text=True,
        )

    def test_파일을_쓴다(self):
        out = self.dir / "out.json"
        self.assertEqual(self.run_cli(self.b, self.o, out).returncode, 0)
        self.assertEqual(json.loads(out.read_text()), {"a": 1, "b": 2})

    def test_check_는_같으면_0_다르면_1(self):
        out = self.dir / "out.json"
        self.run_cli(self.b, self.o, out)
        self.assertEqual(self.run_cli("--check", self.b, self.o, out).returncode, 0)
        out.write_text('{"a": 99}', encoding="utf-8")
        self.assertEqual(self.run_cli("--check", self.b, self.o, out).returncode, 1)

    def test_check_는_대상이_없으면_1(self):
        self.assertEqual(self.run_cli("--check", self.b, self.o, self.dir / "없음").returncode, 1)

    def test_깨진_json_은_1_로_끝나고_이유를_말한다(self):
        self.o.write_text("{ 이건 json 이 아님", encoding="utf-8")
        r = self.run_cli(self.b, self.o, self.dir / "out.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("병합 실패", r.stderr)

    def test_인자_개수가_틀리면_2(self):
        self.assertEqual(self.run_cli(self.b).returncode, 2)

    def test_diff_는_대상이_없어도_실패하지_않는다(self):
        r = self.run_cli("--diff", self.b, self.o, self.dir / "없음")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
