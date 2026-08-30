#!/usr/bin/env python3
"""공통 settings.json 에 호스트별 오버레이를 얹는다.

  merge-settings.py <base> <overlay> <out>
  merge-settings.py --check <base> <overlay> <existing>   # 같으면 exit 0
  merge-settings.py --diff  <base> <overlay> <existing>   # 뭐가 달라지는지 출력

병합 규칙 — 재실행해도 결과가 같도록(멱등) 항상 base 부터 다시 만든다.
  객체   깊게 병합 (오버레이 키가 이김)
  배열   base + overlay 이어붙이고 중복 제거 (permissions.allow, hooks 추가용)
  스칼라 오버레이가 이김
  null   오버레이가 null 이면 그 키를 삭제 (공통 설정을 이 머신에서만 끄는 용도)
"""
import json
import sys


def merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            if v is None:
                out.pop(k, None)
            elif k in out:
                out[k] = merge(out[k], v)
            else:
                out[k] = v
        return out
    if isinstance(base, list) and isinstance(over, list):
        out, seen = [], set()
        for item in base + over:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out
    return over


def render(base_path, overlay_path):
    with open(base_path, encoding="utf-8") as f:
        base = json.load(f)
    with open(overlay_path, encoding="utf-8") as f:
        over = json.load(f)
    over.pop("_comment", None)
    merged = merge(base, over)
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"


def flatten(value, prefix=""):
    """중첩 구조를 "a.b.c" -> 값 으로 편다. 리스트는 통째로 하나의 값이다."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: value}


def _fmt(value, width=58):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= width else text[: width - 1] + "…"


def diff_report(current, merged):
    """지금 설치된 것(current) 을 merged 로 바꿀 때 무엇이 달라지는지."""
    cur, new = flatten(current), flatten(merged)
    lines = []
    for key in sorted(set(cur) | set(new)):
        if key not in new:
            lines.append(f"    삭제  {key}  {_fmt(cur[key])}")
        elif key not in cur:
            lines.append(f"    추가  {key}  {_fmt(new[key])}")
        elif cur[key] != new[key]:
            a, b = cur[key], new[key]
            if isinstance(a, list) and isinstance(b, list):
                gone = [x for x in a if x not in b]
                added = [x for x in b if x not in a]
                if not gone and not added:
                    # 항목은 그대로고 순서만 다르다 (공용에 있던 줄이 오버레이로
                    # 옮겨가면 이렇게 된다). 아무것도 안 찍으면 왜 "변경" 인지 알 수 없다.
                    lines.append(f"    순서  {key}  (항목 {len(a)}개 그대로, 순서만 다름)")
                    continue
                lines.append(f"    변경  {key}  ({len(a)}개 -> {len(b)}개)")
                for x in gone:
                    lines.append(f"            - {_fmt(x, 54)}")
                for x in added:
                    lines.append(f"            + {_fmt(x, 54)}")
            else:
                lines.append(f"    변경  {key}  {_fmt(a, 26)} -> {_fmt(b, 26)}")
    return lines


def main(argv):
    mode = "write"
    if argv and argv[0] in ("--check", "--diff"):
        mode, argv = argv[0][2:], argv[1:]
    check = mode == "check"
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    base_path, overlay_path, target = argv

    try:
        text = render(base_path, overlay_path)
    except (OSError, ValueError) as e:
        print(f"settings 병합 실패: {e}", file=sys.stderr)
        return 1

    if check:
        try:
            with open(target, encoding="utf-8") as f:
                return 0 if f.read() == text else 1
        except OSError:
            return 1

    if mode == "diff":
        try:
            with open(target, encoding="utf-8") as f:
                current = json.load(f)
        except (OSError, ValueError):
            print("    (설치된 settings.json 이 없거나 읽을 수 없음 — 전부 새로 씁니다)")
            return 0
        lines = diff_report(current, json.loads(text))
        print("\n".join(lines) if lines else "    (달라지는 것 없음)")
        return 0

    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
