#!/usr/bin/env python3
"""data/summaries.json 검증: 항목 수·최소 길이·복붙(같은 문장 반복)."""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = 653  # inventory 612 + /context 측정 전용 41


def main() -> int:
    data = json.loads((ROOT / "data" / "summaries.json").read_text(encoding="utf-8"))
    items = data["items"]
    print(f"항목 수: {len(items)} (기대 {EXPECTED})")

    short = [i for i in items if len(i.get("summary", "")) < 30]
    print(f"30자 미만: {len(short)}")
    for i in short[:20]:
        print(f"  {i['kind']} {i['name']}: {i.get('summary','')!r}")

    dup = [(s, c) for s, c in collections.Counter(i["summary"] for i in items).items() if c >= 5]
    print(f"5회 이상 반복된 summary: {len(dup)}")
    for s, c in dup:
        print(f"  {c}회: {s}")

    ok = len(items) == EXPECTED and not short and not dup
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
