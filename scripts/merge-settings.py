#!/usr/bin/env python3
"""공통 settings.json 에 호스트별 오버레이를 얹는다.

  merge-settings.py <base> <overlay> <out>
  merge-settings.py --check <base> <overlay> <existing>   # 같으면 exit 0

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


def main(argv):
    check = argv and argv[0] == "--check"
    if check:
        argv = argv[1:]
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

    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
