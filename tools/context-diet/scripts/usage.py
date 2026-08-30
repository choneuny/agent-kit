#!/usr/bin/env python3
"""usage.py — count per-item invocations from Claude Code transcripts.

Reads ~/.claude/projects/*/*.jsonl line by line (never whole-file) and counts
7d/30d calls for skills, commands, agents and MCP tools, writing data/usage.json.

Counting method: bucket timestamped records into UTC "N days ago" cutoff windows
and count one hit per matching record. The source is the transcripts themselves
and the match key is the item name, not a file path.

Usage:
    uv run scripts/usage.py [--check] [--days-cap 30]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
TRANSCRIPTS = HOME / ".claude" / "projects"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "usage.json"
INVENTORY = ROOT / "data" / "inventory.json"
WINDOWS = [7, 30]
BY = ("human", "hook", "subagent")

# A hook-spawned headless session (`claude -p` from a session-end hook) opens
# with this prompt — the marker that its calls were not typed by a person.
HOOK_SESSION_MARKERS = (
    "Automated hook — no user confirmation",
    "and run /save-session",
)
HOOK_SESSION_HEAD_LINES = 10

# Slash commands the harness handles itself — not inventory items, not context cost.
BUILTIN_SLASH = {
    "clear", "compact", "model", "context", "help", "exit", "quit", "login",
    "logout", "config", "cost", "doctor", "init", "resume", "status", "vim",
    "terminal-setup", "bug", "release-notes", "memory", "agents", "mcp",
    "permissions", "add-dir", "hooks", "export", "ide", "pr-comments",
    "review", "upgrade", "statusline", "todos", "privacy-settings", "artifacts",
    "copy", "plugin", "reload-plugins", "rewind", "usage", "output-style",
}


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def slash_name(text: str):
    """Extract 'foo' from a '<command-name>/foo</command-name>' user record."""
    i = text.find("<command-name>")
    if i < 0:
        return None
    j = text.find("</command-name>", i)
    if j < 0:
        return None
    return text[i + len("<command-name>"):j].strip().lstrip("/").strip() or None


def is_hook_session(path) -> bool:
    """True if this transcript belongs to a session a hook started headlessly."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if n >= HOOK_SESSION_HEAD_LINES:
                    return False
                if any(m in line for m in HOOK_SESSION_MARKERS):
                    return True
    except OSError:
        return False
    return False


def load_inventory_kinds() -> dict[str, str]:
    """name -> kind, for skill/command, so a /foo lands on the right kind."""
    if not INVENTORY.exists():
        return {}
    data = json.loads(INVENTORY.read_text())
    items = data["items"] if isinstance(data, dict) else data
    out = {}
    for it in items:
        if it.get("kind") in ("command", "skill"):
            # command wins ties: a bare /foo is a slash command first.
            if it["kind"] == "command" or it["name"] not in out:
                out[it["name"]] = it["kind"]
    return out


def scan(cap_days: int, name_kinds: dict[str, str]):
    now = datetime.now(timezone.utc)
    cutoffs = {d: now - timedelta(days=d) for d in WINDOWS}
    mtime_floor = time.time() - cap_days * 86400

    calls: dict[tuple[str, str], dict] = defaultdict(
        lambda: {d: 0 for d in WINDOWS} | {"last": None} | {b: 0 for b in BY}
    )
    scanned = 0
    skipped_old = 0
    hook_records = 0

    hook_sessions = 0
    subagent_files = 0

    def hit(kind, name, ts, by):
        rec = calls[(kind, name)]
        for d, c in cutoffs.items():
            if ts >= c:
                rec[d] += 1
                if d == 30:
                    rec[by] += 1
        if rec["last"] is None or ts > rec["last"]:
            rec["last"] = ts

    # Two shapes of transcript: the session's own file, and one file per
    # subagent under <session-uuid>/subagents/ (a `*/*.jsonl` glob misses those
    # — every subagent call was invisible until this was added).
    main_files = sorted(TRANSCRIPTS.glob("*/*.jsonl"))
    sub_files = sorted(TRANSCRIPTS.glob("*/*/subagents/*.jsonl"))
    for path in main_files + sub_files:
        is_sub = path.parent.name == "subagents"
        try:
            if path.stat().st_mtime < mtime_floor:
                skipped_old += 1
                continue
        except OSError:
            continue
        scanned += 1
        if is_sub:
            session_by = "subagent"
        else:
            session_by = "hook" if is_hook_session(path) else "human"
            hook_sessions += session_by == "hook"
        subagent_files += is_sub
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:  # line by line: transcripts reach hundreds of MB
                if '"tool_use"' not in line and "<command-name>" not in line \
                        and '"hook' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if rec.get("attachment", {}).get("type", "").startswith("hook"):
                    hook_records += 1
                by = "subagent" if rec.get("isSidechain") else session_by
                ts = parse_ts(rec.get("timestamp"))
                if ts is None or ts < cutoffs[max(WINDOWS)]:
                    continue
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, str):
                    n = slash_name(content)
                    if n and n not in BUILTIN_SLASH:
                        hit(name_kinds.get(n, "command"), n, ts, by)
                    continue
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        n = slash_name(b.get("text") or "")
                        if n and n not in BUILTIN_SLASH:
                            hit(name_kinds.get(n, "command"), n, ts, by)
                        continue
                    if b.get("type") != "tool_use":
                        continue
                    tool = b.get("name") or ""
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    if tool == "Skill":
                        n = inp.get("skill")
                        if n:
                            hit(name_kinds.get(n, "skill"), n, ts, by)
                    elif tool == "Agent" or tool == "Task":
                        n = inp.get("subagent_type")
                        if n:
                            hit("agent", n, ts, by)
                    elif tool.startswith("mcp__"):
                        hit("mcp_tool", tool, ts, by)
                        parts = tool.split("__")
                        if len(parts) >= 2 and parts[1]:
                            hit("mcp", parts[1], ts, by)

    return calls, scanned, skipped_old, hook_records, hook_sessions, subagent_files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="run skill-stocktake's scan.sh on the same input and compare")
    ap.add_argument("--days-cap", type=int, default=max(WINDOWS),
                    help="skip transcripts whose mtime is older than this (default 30)")
    args = ap.parse_args()

    name_kinds = load_inventory_kinds()
    calls, scanned, skipped_old, hook_records, hook_sessions, subagent_files = scan(args.days_cap, name_kinds)

    items = []
    for (kind, name), rec in calls.items():
        items.append({
            "kind": kind,
            "name": name,
            "calls_7d": rec[7],
            "calls_30d": rec[30],
            "last_used": iso(rec["last"]) if rec["last"] else None,
            "by_30d": {b: rec[b] for b in BY},
        })
    items.sort(key=lambda i: (i["kind"], -i["calls_30d"], i["name"]))

    out = {
        "generated_at": iso(datetime.now(timezone.utc)),
        "window_days": WINDOWS,
        "transcripts_scanned": scanned,
        "transcripts_skipped_old": skipped_old,
        "hook_sessions": hook_sessions,
        "subagent_transcripts": subagent_files,
        "note_by": (
            "by_30d splits the 30d count by caller: subagent = isSidechain record, "
            "hook = a headless session a hook started (a session-end hook running "
            "`claude -p ... /<command>`), human = everything else."
        ),
        "note_hooks": (
            f"hooks are not counted: they fire per session, not per call, and their "
            f"context cost is their output, not their body. {hook_records} hook "
            f"records seen in the scanned window."
        ),
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    # ---- stdout: top 10 per kind
    by_kind = defaultdict(list)
    for it in items:
        by_kind[it["kind"]].append(it)
    print(f"transcripts scanned {scanned} (skipped {skipped_old} older than "
          f"{args.days_cap}d, hook-spawned sessions {hook_sessions}, "
          f"subagent transcripts {subagent_files}) → "
          f"{OUT.relative_to(ROOT)}  items {len(items)}")
    for kind in sorted(by_kind):
        rows = sorted(by_kind[kind], key=lambda i: (-i["calls_30d"], -i["calls_7d"]))[:10]
        print(f"\n{kind}  ({len(by_kind[kind])} items)")
        print(f"  {'name':<40} {'7d':>5} {'30d':>5}  {'사람/훅/서브':>14}  last_used")
        for r in rows:
            b = r["by_30d"]
            print(f"  {r['name'][:40]:<40} {r['calls_7d']:>5} {r['calls_30d']:>5}  "
                  f"{b['human']:>4}/{b['hook']:>4}/{b['subagent']:>4}  {r['last_used'] or '-'}")

    # ---- join against inventory
    if INVENTORY.exists():
        inv = json.loads(INVENTORY.read_text())
        inv_items = inv["items"] if isinstance(inv, dict) else inv
        known = {(i["kind"], i["name"]) for i in inv_items}
        orphans = [i for i in items
                   if i["kind"] != "mcp_tool" and (i["kind"], i["name"]) not in known]
        print(f"\njoin vs inventory.json: {len(items) - len(orphans)}/{len(items)} "
              f"matched, {len(orphans)} in usage but not inventory")
        for o in sorted(orphans, key=lambda i: (i["kind"], i["name"])):
            print(f"  ORPHAN {o['kind']:<9} {o['name']:<40} 30d={o['calls_30d']}")

    if args.check:
        check_by(items, hook_sessions, subagent_files)
        check()
    return 0


def check_by(items, hook_sessions: int, subagent_files: int) -> None:
    """by_30d must partition calls_30d, and the hook-run commands must show it."""
    print("\n--check by: 호출자 구분")
    for it in items:
        s = sum(it["by_30d"].values())
        assert s == it["calls_30d"], f"{it['name']}: by_30d 합 {s} != 30d {it['calls_30d']}"
    tot = {b: sum(i["by_30d"][b] for i in items) for b in BY}
    print(f"  30일 합계 사람 {tot['human']} · 훅 {tot['hook']} · 서브 {tot['subagent']}"
          f"   (훅이 띄운 세션 {hook_sessions}개 · 서브에이전트 트랜스크립트 {subagent_files}개)")
    for name in ("learn-eval", "save-session"):
        it = next((i for i in items if i["kind"] == "command" and i["name"] == name), None)
        if it:
            print(f"  /{name}: {it['by_30d']}")
            assert it["by_30d"]["hook"] > 0, f"/{name} should be hook-driven"
    import subprocess
    n = subprocess.run(["bash", "-c",
        "grep -l -e 'Automated hook — no user confirmation' -e 'and run /save-session' "
        f"{TRANSCRIPTS}/*/*.jsonl 2>/dev/null | wc -l"],
        capture_output=True, text=True).stdout.strip()
    print(f"  독립 재집계: 훅 마커 둘 중 하나를 가진 트랜스크립트 {n}개 vs 훅 세션으로 분류 "
          f"{hook_sessions}개 (차이는 30일 mtime 창 밖 파일)")
    print("  assert ok: by_30d 합이 전 항목에서 30d와 같다")


def check() -> None:
    """Cross-check against skill-stocktake's scan.sh over the same inputs."""
    import subprocess
    scan_sh = HOME / ".agents/skills/skill-stocktake/scripts/scan.sh"
    print(f"\n--check: {scan_sh}")
    if not scan_sh.exists():
        print("  scan.sh not found — cannot compare")
        return
    obs = Path(os.environ.get("SKILL_STOCKTAKE_OBSERVATIONS",
                              HOME / ".claude/observations.jsonl"))
    try:
        res = subprocess.run(["bash", str(scan_sh)], capture_output=True,
                             text=True, timeout=600, cwd=str(ROOT))
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  scan.sh failed to run: {e}")
        return
    if res.returncode != 0:
        print(f"  scan.sh exit {res.returncode}: {res.stderr[-500:]}")
        return
    data = json.loads(res.stdout)
    theirs = {s["name"]: s for s in data["skills"] if s.get("name")}
    ours = {i["name"]: i for i in json.loads(OUT.read_text())["items"]
            if i["kind"] == "skill"}
    print(f"  scan.sh skills: {len(theirs)}   observations file exists: {obs.exists()}")
    if not obs.exists():
        print(f"  NOTE: {obs} missing → scan.sh reports use_7d/use_30d = 0 for every "
              f"skill. Its counts are Read-tool observations, not transcript calls, "
              f"so equality can only be asserted on skills with 0 transcript calls.")
    compared = agree = 0
    disagree = []
    for name, t in theirs.items():
        o = ours.get(name)
        mine7, mine30 = (o["calls_7d"], o["calls_30d"]) if o else (0, 0)
        compared += 1
        if (t["use_7d"], t["use_30d"]) == (mine7, mine30):
            agree += 1
        else:
            disagree.append((name, t["use_7d"], t["use_30d"], mine7, mine30))
    print(f"  compared {compared} skill names: {agree} identical, "
          f"{len(disagree)} differ")
    for name, t7, t30, m7, m30 in sorted(disagree)[:15]:
        print(f"    {name:<40} scan.sh {t7}/{t30}   usage.py {m7}/{m30}")
    overlap = set(theirs) & set(ours)
    print(f"  names present in BOTH scan.sh and usage.py: {len(overlap)} "
          f"{sorted(overlap)[:5]}")
    assert agree >= 1, "no skill matched scan.sh counts — counting methods diverged"
    print("  assert ok: at least one item agrees with scan.sh (see caveat above)")
    recount_independently()


def recount_independently() -> None:
    """The scan.sh comparison is vacuous (see check()), so verify the counts a
    second way: shell grep over the same transcripts, no shared code."""
    import subprocess
    ours = {(i["kind"], i["name"]): i for i in json.loads(OUT.read_text())["items"]}
    probes = [
        ("skill", "docs-upkeep", '"skill":"docs-upkeep"'),
        ("agent", "code-reviewer", '"subagent_type":"code-reviewer"'),
        ("mcp_tool", "mcp__plugin_honcho_honcho__search",
         '"name":"mcp__plugin_honcho_honcho__search"'),
    ]
    print("\n  independent recount (grep over the same *.jsonl, 30d window):")
    ok = 0
    for kind, name, pat in probes:
        mine = ours.get((kind, name))
        if not mine:
            print(f"    {name}: absent from usage.json — skipped")
            continue
        res = subprocess.run(
            ["bash", "-c", f'grep -oF {json.dumps(pat)} '
                           f'{TRANSCRIPTS}/*/*.jsonl 2>/dev/null | wc -l'],
            capture_output=True, text=True)
        grep_n = int(res.stdout.strip() or 0)
        mark = "==" if grep_n == mine["calls_30d"] else ">=" 
        print(f"    {kind}/{name}: usage.py 30d={mine['calls_30d']} {mark} grep {grep_n}"
              + ("" if grep_n == mine["calls_30d"]
                 else "  (grep has no time window; extra hits predate 30d)"))
        # grep counts every occurrence in every file, with no 30d cutoff, so it is
        # an upper bound on our windowed count.
        assert grep_n >= mine["calls_30d"], (
            f"{name}: usage.py {mine['calls_30d']} > grep {grep_n}")
        ok += grep_n == mine["calls_30d"]
    assert ok >= 1, "no probe matched grep exactly — counting logic diverged"
    print(f"  assert ok: {ok} item(s) recounted identically by grep")


if __name__ == "__main__":
    sys.exit(main())
