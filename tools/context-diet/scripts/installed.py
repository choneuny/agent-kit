#!/usr/bin/env python3
"""installed.py — when did each item arrive?

  uv run scripts/installed.py            # -> data/installed.json
  uv run scripts/installed.py --check    # + re-derive a sample a second way

Source order (best evidence first), recorded per item in `confidence`:

  plugin-meta      ~/.claude/plugins/installed_plugins.json `installedAt`
  agents-git       first commit that added the file to ~/.agents (the canonical
                   repo for rules and skills)
  birth-time       filesystem birth time (`stat -c %W`; ext4 on this box records
                   it — python has no st_birthtime on Linux, hence the shell)
  transcript-first the day the name first shows up in ~/.claude/projects/*.jsonl
                   (MCP servers have no file: `mcp__<server>__` is the only trace)
  none             nothing found — the field stays null rather than guessing

Floors, not birthdays: ~/.agents was seeded on 2026-08-14 and ~/.claude was
copied to this box on 2026-07-03 (devbox migration), so git and birth times
never predate those. An item older than its store reads as that store's date.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HOME = Path.home()
AGENTS_REPO = HOME / ".agents"
TRANSCRIPTS = HOME / ".claude/projects"
PLUGINS_JSON = HOME / ".claude/plugins/installed_plugins.json"

TS_RE = re.compile(r'"timestamp":"([0-9T:.\-]+Z)"')
MCP_RE = re.compile(r"mcp__([A-Za-z0-9_.-]+?)__")


def load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── sources ───────────────────────────────────────────────────────────────────
def plugin_installed_at() -> dict[str, str]:
    """'<plugin>@<market>' -> installedAt"""
    if not PLUGINS_JSON.is_file():
        return {}
    doc = json.loads(PLUGINS_JSON.read_text(encoding="utf-8"))
    out = {}
    for key, entries in (doc.get("plugins") or {}).items():
        for e in entries:
            if e.get("installedAt"):
                out[key] = e["installedAt"]
                break
    return out


def git_first_commits() -> dict[str, str]:
    """repo-relative path -> author date of the commit that added it."""
    if not (AGENTS_REPO / ".git").exists():
        return {}
    # One walk of the history beats one `git log` per file (77 rules + 44 skills).
    r = subprocess.run(
        ["git", "-C", str(AGENTS_REPO), "log", "--diff-filter=A", "--reverse",
         "--format=@%aI", "--name-only"],
        capture_output=True, text=True, timeout=120)
    out: dict[str, str] = {}
    when = None
    for line in r.stdout.splitlines():
        if line.startswith("@"):
            when = line[1:]
        elif line.strip() and when:
            out.setdefault(line.strip(), when)
    return out


def birth_times(paths: list[str]) -> dict[str, str]:
    """path -> birth time, for the paths where the filesystem kept one."""
    out: dict[str, str] = {}
    for i in range(0, len(paths), 200):
        chunk = paths[i:i + 200]
        r = subprocess.run(["stat", "-c", "%W\t%n", *chunk],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            secs, _, path = line.partition("\t")
            try:
                s = int(secs)
            except ValueError:
                continue
            if s > 0:
                out[path] = iso(datetime.fromtimestamp(s, timezone.utc))
    return out


def transcript_first_seen(servers: set[str]) -> tuple[dict[str, str], int, int]:
    """Earliest timestamp each MCP server name appears in any transcript.

    Full history, so no mtime filter — every *.jsonl gets read line by line
    (never whole-file: some are hundreds of MB)."""
    first: dict[str, str] = {}
    files = scanned = 0
    for path in sorted(TRANSCRIPTS.glob("*/*.jsonl")):
        files += 1
        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        with fh:
            for line in fh:
                if "mcp__" not in line:
                    continue
                names = {n for n in MCP_RE.findall(line) if n in servers}
                names |= {n for n in MCP_RE.findall(line)
                          if n.startswith("plugin_") and n.split("_")[-1] in servers}
                if not names:
                    continue
                m = TS_RE.search(line)
                if not m:
                    continue
                ts = m.group(1)
                for n in names:
                    key = n.split("_")[-1] if n.startswith("plugin_") else n
                    if key not in first or ts < first[key]:
                        first[key] = ts
    return {k: v.split(".")[0] + "Z" for k, v in first.items()}, files, scanned


# ── build ─────────────────────────────────────────────────────────────────────
def build() -> dict:
    inv = load("inventory.json").get("items", [])
    meas = load("context-measured.json")
    plug = plugin_installed_at()
    git = git_first_commits()

    # every item that can carry a date: inventory rows + the MCP servers that
    # only /context knows about (built-ins, app connectors)
    rows: list[dict] = [
        {"kind": i["kind"], "name": i["name"], "path": i.get("path"),
         "plugin": i.get("plugin")} for i in inv]
    known_mcp = {(r["kind"], r["name"]) for r in rows if r["kind"] == "mcp"}
    for server in meas.get("mcp", {}).get("by_server", {}):
        if ("mcp", server) not in known_mcp:
            rows.append({"kind": "mcp", "name": server, "path": None, "plugin": None})

    paths = sorted({r["path"] for r in rows if r["path"] and Path(r["path"]).exists()})
    births = birth_times(paths)
    servers = {r["name"] for r in rows if r["kind"] == "mcp"}
    first_seen, files, scanned = transcript_first_seen(servers)

    items = []
    for r in rows:
        at = source = None
        if r["plugin"] and plug.get(r["plugin"]):
            at, source = plug[r["plugin"]], "plugin-meta"
        elif r["path"] and str(r["path"]).startswith(str(AGENTS_REPO)):
            rel = str(Path(r["path"]).resolve()).replace(str(AGENTS_REPO) + "/", "")
            if git.get(rel):
                at, source = git[rel], "agents-git"
        # an MCP server's "path" is the shared ~/.claude.json — its birth time is
        # when that config was last rewritten, not when the server arrived.
        if at is None and r["kind"] != "mcp" and r["path"] and births.get(r["path"]):
            at, source = births[r["path"]], "birth-time"
        if at is None and r["kind"] == "mcp" and first_seen.get(r["name"].split(":")[-1]):
            r_name = r["name"].split(":")[-1]
            at, source = first_seen[r_name], "transcript-first"
        items.append({
            "kind": r["kind"], "name": r["name"], "path": r["path"],
            "installed_at": iso(datetime.fromisoformat(at.replace("Z", "+00:00"))) if at else None,
            "source": source,
            "confidence": source or "none",
        })
    items.sort(key=lambda i: (i["kind"], i["name"]))
    return {
        "generated_at": iso(datetime.now(timezone.utc)),
        "sources": {
            "plugin-meta": str(PLUGINS_JSON),
            "agents-git": f"git -C {AGENTS_REPO} log --diff-filter=A --reverse --format=@%aI --name-only",
            "birth-time": "stat -c %W <path>",
            "transcript-first": f"{scanned}/{files} transcripts scanned for mcp__<server>__",
        },
        "caveats": [
            "~/.agents는 2026-08-14에 정본으로 세워졌다 — git 첫 커밋은 그날이 바닥이고 "
            "규칙이 실제로 태어난 날은 그보다 이를 수 있다",
            "~/.claude 파일 다수의 birth time은 2026-07-03(devbox 이사로 복사된 날)이다 — "
            "설치일이 아니라 이 기계에 온 날이다",
            "MCP 서버는 파일이 없어 트랜스크립트 첫 등장만 있다 — 그것은 처음 쓴 날이지 "
            "설치한 날이 아니다(설치 후 안 쓰다 나중에 처음 부르면 늦게 잡힌다)",
        ],
        "items": items,
    }


# ── check ─────────────────────────────────────────────────────────────────────
def check(doc: dict) -> int:
    items = doc["items"]
    bad = 0
    order = ["plugin-meta", "agents-git", "birth-time", "transcript-first", "none"]
    counts = {s: sum(1 for i in items if i["confidence"] == s) for s in order}
    print("출처별 건수: " + " · ".join(f"{s} {counts[s]}" for s in order))

    for i in items:
        if (i["installed_at"] is None) != (i["source"] is None):
            print(f"FAIL 시각과 출처가 어긋난다: {i['kind']}:{i['name']}")
            bad += 1
    # priority: an ~/.agents file with a git date must not have fallen back to birth
    for i in items:
        if i["source"] == "birth-time" and i["path"] and str(i["path"]).startswith(str(AGENTS_REPO)):
            r = subprocess.run(["git", "-C", str(AGENTS_REPO), "log", "--diff-filter=A",
                                "--format=%aI", "--", i["path"]], capture_output=True, text=True)
            if r.stdout.strip():
                print(f"FAIL git 날짜가 있는데 birth-time을 썼다: {i['path']}")
                bad += 1

    # re-derive one item per source, independently
    print("\n표본 재확인 (출처마다 하나, 다른 명령으로):")
    for src in order[:-1]:
        s = next((i for i in items if i["confidence"] == src), None)
        if not s:
            print(f"  {src}: 표본 없음")
            continue
        if src == "plugin-meta":
            key = next(i.get("plugin") for i in load("inventory.json")["items"]
                       if i["kind"] == s["kind"] and i["name"] == s["name"])
            r = subprocess.run(["python3", "-c",
                                f"import json;d=json.load(open({json.dumps(str(PLUGINS_JSON))}));"
                                f"print(d['plugins'][{json.dumps(key)}][0]['installedAt'])"],
                               capture_output=True, text=True)
            got = r.stdout.strip()
        elif src == "agents-git":
            r = subprocess.run(["bash", "-c",
                                f"git -C {AGENTS_REPO} log --diff-filter=A --format=%aI -- "
                                f"{json.dumps(s['path'])} | tail -1"], capture_output=True, text=True)
            got = r.stdout.strip()
        elif src == "birth-time":
            r = subprocess.run(["stat", "-c", "%W", s["path"]], capture_output=True, text=True)
            secs = int(r.stdout.strip() or 0)
            got = iso(datetime.fromtimestamp(secs, timezone.utc)) if secs else ""

        else:
            r = subprocess.run(["bash", "-c",
                                f"grep -l 'mcp__{s['name']}__' {TRANSCRIPTS}/*/*.jsonl 2>/dev/null | head -1"],
                               capture_output=True, text=True)
            got = r.stdout.strip() or "(없음)"
        same = (s["installed_at"][:10] in got) if (got and s["installed_at"] and src != "transcript-first") else None
        print(f"  {src:16} {s['kind']}:{s['name'][:34]:<34} {s['installed_at']}  ← {got[:60]}"
              + ("" if same is None else ("  일치" if same else "  ✗ 불일치")))
        if same is False:
            bad += 1
    print("\n--check ok" if not bad else f"\n--check FAILED ({bad})")
    return bad


def main() -> int:
    doc = build()
    out = DATA / "installed.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    got = sum(1 for i in doc["items"] if i["installed_at"])
    print(f"wrote {out} ({out.stat().st_size:,} bytes, 항목 {len(doc['items'])}개, 시각 확보 {got}개)")
    for s in ("plugin-meta", "agents-git", "birth-time", "transcript-first", "none"):
        print(f"  {s:16} {sum(1 for i in doc['items'] if i['confidence'] == s)}")
    if "--check" in sys.argv:
        return check(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
