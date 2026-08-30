#!/usr/bin/env python3
"""Batch inputs for the qualitative judgment pass, and merge the sub-agent results.

  uv run scripts/judge.py prepare    # data/judgments/batch-<kind>-<n>.input.json
  uv run scripts/judge.py merge      # data/judgments/batch-*.json -> data/judgments.json
  uv run scripts/judge.py --check    # validate data/judgments.json against the target set

Targets = every enabled item in inventory.json, plus items that only exist in the
/context measurement (built-in MCP servers, built-in skills). Measured-only naming
follows ui/src/merge.js: kind + the measured row's name.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BATCHES = DATA / "judgments"
BATCH_SIZE = 15
VERDICTS = {"Keep", "Improve", "Update", "Retire", "Merge"}


def load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def key(kind: str, name: str) -> str:
    return f"{kind}\t{name}"


def targets() -> list[dict]:
    """Every item that occupies context in a live session, with all the evidence a
    judge needs before opening the file."""
    inv = load("inventory.json")
    measured = load("context-measured.json")
    usage = {key(u["kind"], u["name"]): u for u in load("usage.json").get("items", [])}

    items = inv.get("items", [])
    inv_names = {i["name"] for i in items}
    inv_keys = {key(i["kind"], i["name"]) for i in items}

    m_skill = {s["name"]: s["tokens"] for s in measured.get("skills", [])}
    m_agent = {a["name"]: a["tokens"] for a in measured.get("agents", [])}
    m_mem = {m["path"]: m["tokens"] for m in measured.get("memory_files", [])}
    m_server = measured.get("mcp", {}).get("by_server", {})
    mcp_tools: dict[str, list] = {}
    for t in measured.get("mcp", {}).get("tools", []):
        mcp_tools.setdefault(t["server"], []).append({"name": t["name"], "tokens": t["tokens"]})

    out = []

    def add(kind, name, **extra):
        u = usage.get(key(kind, name), {})
        out.append({
            "kind": kind, "name": name,
            "usage": {"calls_7d": u.get("calls_7d"), "calls_30d": u.get("calls_30d"),
                      "last_used": u.get("last_used")},
            **extra,
        })

    for i in items:
        if not i.get("enabled"):
            continue
        measured_tokens = None
        if i["kind"] == "memory" or i["kind"] == "rule":
            measured_tokens = m_mem.get(i["path"])
        elif i["kind"] == "skill":
            measured_tokens = m_skill.get(i["name"])
        elif i["kind"] == "agent":
            measured_tokens = m_agent.get(i["name"])
        elif i["kind"] == "mcp":
            measured_tokens = (m_server.get(i["name"]) or {}).get("tokens")
        add(i["kind"], i["name"],
            path=i.get("path"), bytes=i.get("bytes"),
            tokens_est=i.get("tokens_est"), tokens_body_est=i.get("tokens_body_est"),
            listing_bytes=i.get("listing_bytes"), source=i.get("source"),
            plugin=i.get("plugin"), mtime=i.get("mtime"), note=i.get("note"),
            measured_tokens=measured_tokens,
            mcp_tools=mcp_tools.get(i["name"]) if i["kind"] == "mcp" else None)

    # measured-only: built-in servers and skills the harness ships with. Skip names that
    # already exist under another kind (commands are listed as "Skills" by /context).
    for server, agg in m_server.items():
        if key("mcp", server) in inv_keys:
            continue
        add("mcp", server, path=None, bytes=None, tokens_est=None, tokens_body_est=None,
            listing_bytes=None, source="실측 표본", plugin=None, mtime=None,
            note="하네스 내장 — 파일이 없다", measured_tokens=agg["tokens"],
            mcp_tools=mcp_tools.get(server))
    for kind, table in (("skill", m_skill), ("agent", m_agent)):
        for name, tokens in table.items():
            if key(kind, name) in inv_keys or name in inv_names:
                continue
            add(kind, name, path=None, bytes=None, tokens_est=None, tokens_body_est=None,
                listing_bytes=None, source="실측 표본", plugin=None, mtime=None,
                note="하네스 내장 — 파일이 없다", measured_tokens=tokens, mcp_tools=None)
    return out


def cmd_prepare() -> int:
    tgt = targets()
    done = {key(j["kind"], j["name"]): j
            for j in load("judgments.json").get("items", [])}
    BATCHES.mkdir(parents=True, exist_ok=True)
    for old in BATCHES.glob("batch-*.input.json"):
        old.unlink()

    todo: dict[str, list] = {}
    cached = 0
    for t in tgt:
        prev = done.get(key(t["kind"], t["name"]))
        if prev and prev.get("mtime") == t.get("mtime"):
            cached += 1
            continue
        todo.setdefault(t["kind"], []).append(t)

    written = 0
    for kind, group in sorted(todo.items()):
        nb = max(1, (len(group) + BATCH_SIZE - 1) // BATCH_SIZE)  # even split, no runt batch
        for n in range(nb):
            chunk = group[n * len(group) // nb:(n + 1) * len(group) // nb]
            p = BATCHES / f"batch-{kind}-{n + 1}.input.json"
            p.write_text(json.dumps({"kind": kind, "items": chunk}, ensure_ascii=False,
                                    indent=2), encoding="utf-8")
            print(f"{p}  {len(chunk)}")
            written += 1
    print(f"\ntargets {len(tgt)} · cached {cached} · batches {written}")
    return 0


def cmd_merge() -> int:
    tgt = {key(t["kind"], t["name"]): t for t in targets()}
    merged = {key(j["kind"], j["name"]): j
              for j in load("judgments.json").get("items", [])}

    for p in sorted(BATCHES.glob("batch-*.json")):
        if p.name.endswith(".input.json"):
            continue
        for j in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            k = key(j["kind"], j["name"])
            t = tgt.get(k)
            prev = merged.get(k)
            if prev and t and prev.get("mtime") == t.get("mtime"):
                continue  # unchanged since it was judged; keep the old verdict
            merged[k] = {
                "kind": j["kind"], "name": j["name"],
                "path": j.get("path") or (t or {}).get("path"),
                "verdict": j["verdict"], "merge_into": j.get("merge_into") or None,
                "reason": j["reason"], "confidence": j.get("confidence", "medium"),
                "judged_at": j.get("judged_at") or datetime.now(timezone.utc).isoformat(),
                "mtime": (t or {}).get("mtime"),
            }

    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "items": [merged[k] for k in sorted(merged)]}
    (DATA / "judgments.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"judgments.json: {len(out['items'])} items")
    return 0


def cmd_check() -> int:
    tgt = {key(t["kind"], t["name"]) for t in targets()}
    items = load("judgments.json").get("items", [])
    bad = []
    seen = set()
    for j in items:
        k = key(j["kind"], j["name"])
        if k in seen:
            bad.append(f"duplicate: {k}")
        seen.add(k)
        if j.get("verdict") not in VERDICTS:
            bad.append(f"bad verdict {j.get('verdict')!r}: {k}")
        if j.get("verdict") == "Merge" and not j.get("merge_into"):
            bad.append(f"Merge without merge_into: {k}")
        r = j.get("reason") or ""
        if len(r) < 80:
            bad.append(f"reason too short ({len(r)}): {k}")
        if not any("가" <= c <= "힣" for c in r):
            bad.append(f"reason not Korean: {k}")
    for k in sorted(tgt - seen):
        bad.append(f"missing: {k}")
    # 꺼진 항목의 옛 판정은 문제가 아니다 — 재고 어디에도 없는 이름만 짚는다
    known = {key(i["kind"], i["name"]) for i in load("inventory.json").get("items", [])} | tgt
    for k in sorted(seen - known):
        bad.append(f"unknown name: {k}")

    print(f"targets {len(tgt)} · items {len(items)}")
    if bad:
        print(f"\n{len(bad)} problems:")
        for b in bad[:40]:
            print("  " + b)
        return 1
    print("--check ok")
    return 0


def summary() -> None:
    items = load("judgments.json").get("items", [])
    if not items:
        return
    from collections import Counter
    vc = Counter(j["verdict"] for j in items)
    kc = Counter((j["kind"], j["verdict"]) for j in items)
    print("\nverdict:", "  ".join(f"{v} {n}" for v, n in vc.most_common()))
    kinds = sorted({k for k, _ in kc})
    order = ["Retire", "Merge", "Update", "Improve", "Keep"]
    print(f"{'kind':<9}" + "".join(f"{v:>9}" for v in order) + f"{'total':>9}")
    for k in kinds:
        row = [kc.get((k, v), 0) for v in order]
        print(f"{k:<9}" + "".join(f"{n:>9}" for n in row) + f"{sum(row):>9}")
    # 상위는 상주 토큰(실측 우선, 없으면 추정) 내림차순 — 빼서 이득이 큰 순서
    cost = {key(t["kind"], t["name"]): (t.get("measured_tokens") or t.get("tokens_est") or 0)
            for t in targets()}
    top = sorted((j for j in items if j["verdict"] in ("Retire", "Merge")),
                 key=lambda j: -cost.get(key(j["kind"], j["name"]), 0))
    print("\nRetire / Merge 상위 15 (상주 토큰 순):")
    for j in top[:15]:
        tail = f" -> {j['merge_into']}" if j.get("merge_into") else ""
        c = cost.get(key(j["kind"], j["name"]), 0)
        print(f"  {c:>7,}  {j['verdict']:<7} {j['kind']:<8} {j['name']}{tail}")


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if "--check" in args:
        rc = cmd_check()
        summary()
        return rc
    if "prepare" in args:
        return cmd_prepare()
    if "merge" in args:
        rc = cmd_merge()
        summary()
        return rc
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
