#!/usr/bin/env python3
"""Build the decision cards — one card per handle the user can actually pull.

  uv run scripts/decisions.py            # -> data/decisions.json
  uv run scripts/decisions.py --check    # validate the file just written

The card list itself lives in cards.py — it names one machine's handles, so it
is meant to be rewritten per environment; docs/guides/decision-cards.md carries
the data contract and the rewriting procedure. Token numbers prefer the
/context measurement (data/context-measured.json); the calibrated estimate is
the fallback.

Hook cost is the hook's *output*, not its script body. Read-only hooks are run
here; the ones that write files are read off the session transcript instead
(a SessionStart hook attachment records exactly what got injected).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HOME = Path.home()
PAIR_LIMIT = 6000

# A session whose first records hold the SessionStart hook injections.
# Set CONTEXT_DIET_TRANSCRIPT to a session .jsonl whose first records hold the
# SessionStart hook injections; without it the hook-output card is skipped.
TRANSCRIPT = Path(os.environ["CONTEXT_DIET_TRANSCRIPT"]) if os.environ.get("CONTEXT_DIET_TRANSCRIPT") else None

HOWTO = {
    "rule": "~/.claude/rules/<이름>.md 심링크를 ~/.claude/rules/.disabled/로 옮긴다",
    "skill": "~/.claude/skills/<이름> 심링크를 .disabled/로 옮긴다",
    "command": "~/.claude/commands/<이름>.md를 ~/.claude/commands/.disabled/로 옮긴다",
    "agent": "~/.claude/agents/<이름>.md를 ~/.claude/agents/.disabled/로 옮긴다",
    "hook": "~/.claude/settings.json의 해당 hook 항목을 제거한다 (settings.json.bak-<시각> 먼저)",
    "mcp": "~/.claude.json의 mcpServers에서 그 서버를 disabledMcpServers 쪽으로 옮긴다",
    "plugin": "~/.claude/settings.json의 enabledPlugins에서 <플러그인>@<마켓>을 false로",
    "memory": "끄지 못한다 — 본문을 줄이는 수밖에 없다",
    "builtin": "끄지 못한다 — 사유 표시만",
    "connector": "앱 설정에서",
}


def load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── token estimate ────────────────────────────────────────────────────────────
CAL = load("calibration.json")
A = CAL.get("ascii_div") or 4.0
B = CAL.get("non_ascii_per_char") or 1.5


def est_text(text: str) -> int:
    ascii_bytes = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = sum(1 for ch in text if ord(ch) >= 128)
    return round(ascii_bytes / A + non_ascii * B)


def read_text(path: str | Path, limit: int | None = None) -> str:
    try:
        t = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return t if limit is None else t[:limit]


# ── evidence sources ──────────────────────────────────────────────────────────
INV = load("inventory.json")
ITEMS = INV.get("items", [])
MEAS = load("context-measured.json")
JUDG = {(i["kind"], i["name"]): i for i in load("judgments.json").get("items", [])}
USAGE = load("usage.json").get("items", [])
SUMM = {(i["kind"], i["name"]): i.get("summary") for i in load("summaries.json").get("items", [])}

MEAS_MEMORY = {m["path"]: m["tokens"] for m in MEAS.get("memory_files", [])}
MEAS_AGENT = {a["name"]: a["tokens"] for a in MEAS.get("agents", [])}
MEAS_SKILL = {s["name"]: s["tokens"] for s in MEAS.get("skills", [])}
MEAS_MCP = MEAS.get("mcp", {}).get("by_server", {})
MEAS_MCP_TOOLS = MEAS.get("mcp", {}).get("tools", [])

ENABLED = [i for i in ITEMS if i.get("enabled")]


def inv_of(kind: str, pred) -> list[dict]:
    return [i for i in ENABLED if i["kind"] == kind and pred(i)]


def item_tokens(i: dict) -> tuple[int, str]:
    """(tokens, basis) for one inventory item — measured row wins."""
    kind, name = i["kind"], i["name"]
    if kind in ("rule", "memory") and i["path"] in MEAS_MEMORY:
        return MEAS_MEMORY[i["path"]], "measured"
    if kind == "agent" and name in MEAS_AGENT:
        return MEAS_AGENT[name], "measured"
    if kind in ("skill", "command") and name in MEAS_SKILL:
        return MEAS_SKILL[name], "measured"
    return i.get("tokens_est") or 0, "estimated"


def verdicts_for(items: list[dict]) -> list[dict]:
    out = []
    for i in items:
        j = JUDG.get((i["kind"], i["name"]))
        if not j:
            continue
        out.append({
            "name": i["name"],
            "verdict": j["verdict"],
            "merge_into": j.get("merge_into"),
            "reason": j.get("reason"),
        })
    return out


def usage_for(kinds_names: list[tuple[str, str]]) -> dict | None:
    rows = [u for u in USAGE if (u["kind"], u["name"]) in set(kinds_names)]
    if not rows:
        return {"calls_30d": 0, "calls_7d": 0, "last_used": None, "top": []}
    rows.sort(key=lambda u: -u["calls_30d"])
    return {
        "calls_30d": sum(u["calls_30d"] for u in rows),
        "calls_7d": sum(u["calls_7d"] for u in rows),
        "last_used": max((u["last_used"] for u in rows if u.get("last_used")), default=None),
        "top": [{"name": u["name"], "calls": u["calls_30d"]} for u in rows[:5]],
    }


# ── breaks: grep the real files ───────────────────────────────────────────────
GREP_LOG: list[dict] = []


def grep_files(pattern: str, paths: list[Path], label: str) -> list[tuple[Path, str]]:
    """Case-insensitive substring scan. Returns (path, first matching line)."""
    rx = re.compile(pattern, re.I)
    hits = []
    for p in paths:
        txt = read_text(p)
        for line in txt.splitlines():
            if rx.search(line):
                hits.append((p, line.strip()[:200]))
                break
    GREP_LOG.append({"label": label, "pattern": pattern, "files": len(paths), "hits": len(hits)})
    return hits


def glob_many(*globs: str) -> list[Path]:
    out: list[Path] = []
    for g in globs:
        base, _, pat = g.partition("*")
        root = Path(base).expanduser()
        parent = root if root.is_dir() else root.parent
        try:
            out.extend(sorted(parent.glob("*" + pat) if pat else parent.iterdir()))
        except OSError:
            pass
    return [p for p in out if p.is_file()]


# ~/.claude/skills holds per-skill symlinks into ~/.agents/skills — dedupe by
# realpath or every hit is reported twice.
SKILL_MDS = sorted(
    {p.resolve(): p for p in
     list((HOME / ".agents/skills").glob("*/SKILL.md")) + list((HOME / ".claude/skills").glob("*/SKILL.md"))
     }.values()
)
COMMAND_MDS = sorted((HOME / ".claude/commands").glob("*.md"))
RULE_MDS = sorted((HOME / ".agents/rules/common").glob("*.md"))
AGENT_MDS = sorted((HOME / ".claude/agents").glob("*.md"))
HOOK_SCRIPTS = sorted((HOME / ".claude/scripts").glob("*.sh"))


KIND_KO = {"rule": "규칙", "skill": "스킬", "command": "명령", "agent": "에이전트"}


def brk(what: str, how: str, evidence: str | None = None, target_id: str | None = None) -> dict:
    """One break row. `how` is a sentence for the screen; `evidence` is the raw
    line it came from; `target_id` is the map.json node so the UI can highlight
    by id instead of guessing from the name."""
    return {"what": what, "how": how, "evidence": evidence, "target_id": target_id}


def mcp_breaks(server: str) -> tuple[list[dict], str]:
    """Who mentions this MCP server by name."""
    hits = grep_files(re.escape(server), SKILL_MDS + COMMAND_MDS + RULE_MDS + AGENT_MDS, f"mcp:{server}")
    breaks = []
    for p, line in hits:
        if p.parent.name == "common":
            kind = "rule"
        elif p.name == "SKILL.md":
            kind = "skill"
        elif p.parent.name == "commands":
            kind = "command"
        else:
            kind = "agent"
        name = p.parent.name if p.name == "SKILL.md" else p.stem
        ko = KIND_KO[kind]
        summary = SUMM.get((kind, name))
        # No Korean particle after the server name — they are English words and
        # the right particle depends on the last letter.
        tail = f"본문에 서버 이름이 나온다: {server} (도구 호출까지는 미확인)"
        how = f"{summary} — 그 {ko} {tail}" if summary else f"{ko} {name}의 {tail}"
        breaks.append(brk(f"{ko} {name}", how, evidence=line, target_id=f"{kind}:{name}"))
    note = (
        f"grep -ril '{server}' ~/.agents/skills/*/SKILL.md ~/.claude/skills/*/SKILL.md "
        f"~/.claude/commands ~/.agents/rules/common ~/.claude/agents"
    )
    return breaks, note


# ── hook output measurement ───────────────────────────────────────────────────
def transcript_hook_outputs() -> dict[str, dict]:
    """Real SessionStart injections from the transcript, keyed by command string."""
    out: dict[str, dict] = {}
    if TRANSCRIPT is None or not TRANSCRIPT.is_file():
        return out
    with TRANSCRIPT.open(encoding="utf-8") as f:
        for n, line in enumerate(f):
            if n > 60:
                break
            try:
                d = json.loads(line)
            except ValueError:
                continue
            a = d.get("attachment") or {}
            if a.get("type") != "hook_success":
                continue
            text = a.get("content") or ""
            if not text:
                # stdout is a hook JSON envelope; the injected part is additionalContext
                try:
                    env = json.loads(a.get("stdout") or "{}")
                    text = (env.get("hookSpecificOutput") or {}).get("additionalContext") or ""
                except ValueError:
                    text = a.get("stdout") or ""
            out[a.get("command") or f"hook#{n}"] = {
                "chars": len(text),
                "tokens": est_text(text),
                "hook_event": a.get("hookEvent"),
            }
    return out


TRANSCRIPT_HOOKS = transcript_hook_outputs()


def transcript_match(needle: str) -> dict | None:
    for cmd, v in TRANSCRIPT_HOOKS.items():
        if needle in cmd:
            return v
    return None


def run_capture(cmd: list[str], stdin: str = "", cwd: str | None = None) -> str | None:
    try:
        r = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, timeout=20,
            cwd=cwd, env={**os.environ, "CLAUDE_HOOK_ACTIVE": ""},
        )
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def injected_from_stdout(stdout: str) -> str:
    try:
        env = json.loads(stdout)
    except ValueError:
        return stdout
    hso = env.get("hookSpecificOutput") or {}
    return hso.get("additionalContext") or env.get("additionalContext") or stdout




# ── cards ─────────────────────────────────────────────────────────────────────
def card(**kw) -> dict:
    kw.setdefault("usage", None)
    kw.setdefault("breaks", [])
    kw.setdefault("replacement", None)
    kw.setdefault("verdicts", [])
    kw.setdefault("pair", None)
    kw.setdefault("note", None)
    kw["tokens"].setdefault("parts", [])
    return kw


def mcp_card(server: str, group: int, title: str, replacement: str | None = None) -> dict:
    meas = MEAS_MCP.get(server, {})
    tokens = meas.get("tokens", 0)
    parts = sorted(
        [{"name": t["name"].split("__")[-1], "tokens": t["tokens"]}
         for t in MEAS_MCP_TOOLS if t["server"] == server],
        key=lambda p: -p["tokens"])
    breaks, note = mcp_breaks(server)
    j = JUDG.get(("mcp", server))
    return card(
        id=f"mcp:{server}", group=group, title=title, unit="MCP 서버",
        tokens={"reclaim": tokens, "basis": "measured" if tokens else "estimated", "parts": parts},
        usage=usage_for([("mcp", server), ("mcp", f"plugin_{server}")]),
        breaks=breaks, note=note, replacement=replacement,
        verdicts=verdicts_for([{"kind": "mcp", "name": server}]) if j else [],
        options=["keep", "remove", "hold"], howto=HOWTO["mcp"],
    )


def dir_card(kind: str, dirpaths: list[str], group: int, title: str, extra_breaks=None) -> dict:
    items = inv_of(kind, lambda i: any(i["path"].startswith(d) for d in dirpaths))
    parts, total, basis = [], 0, "measured"
    for i in sorted(items, key=lambda i: i["name"]):
        t, b = item_tokens(i)
        if b != "measured":
            basis = "mixed"
        parts.append({"name": i["name"], "tokens": t})
        total += t
    parts.sort(key=lambda p: -p["tokens"])
    return card(
        id=f"dir:{kind}", group=group, title=title,
        unit="로컬 디렉터리", tokens={"reclaim": total, "basis": basis, "parts": parts},
        usage=usage_for([(kind, i["name"]) for i in items]),
        breaks=extra_breaks or [],
        verdicts=verdicts_for(items),
        options=["keep", "remove", "shrink", "hold"], howto=HOWTO[kind],
    )


def rule_item(name: str) -> dict | None:
    return next((i for i in ENABLED if i["kind"] == "rule" and i["name"] == name), None)


def rule_pair(a_name: str, b_name: str) -> dict | None:
    a, b = rule_item(a_name), rule_item(b_name)
    if not a or not b:
        return None
    def side(i):
        txt = read_text(i["path"])
        return {"name": i["name"], "path": i["path"],
                "text": txt[:PAIR_LIMIT], "truncated": len(txt) > PAIR_LIMIT}
    return {"a": side(a), "b": side(b)}




# ── check ─────────────────────────────────────────────────────────────────────
def check(doc: dict) -> int:
    items = doc["items"]
    bad = 0
    ids = [i["id"] for i in items]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"FAIL 중복 id: {sorted(dupes)}")
        bad += 1
    groups = {i["group"] for i in items}
    missing = sorted(set(range(1, 9)) - groups)
    if missing:
        print(f"FAIL 빠진 group: {missing}")
        bad += 1
    for c in items:
        for v in c["verdicts"]:
            if v["verdict"] == "Merge" and v.get("merge_into") and c["unit"] == "규칙 파일":
                if c.get("pair"):
                    continue
                # 합칠 상대가 이미 없어졌으면 판정이 실행으로 소화된 것이다 — 실패가 아니다
                if rule_item(v["merge_into"]):
                    print(f"FAIL Merge 카드에 pair 없음: {c['id']}")
                    bad += 1
                else:
                    print(f"주의 합칠 상대 {v['merge_into']}가 이제 없다 — 판정이 낡았다: {c['id']}")

    rows = [b for c in items for b in c["breaks"]]
    with_id = sum(1 for b in rows if b.get("target_id"))
    dumped = [b for b in rows if b["how"].startswith("description:") or len(b["how"]) > 200]
    print(f"breaks {len(rows)}줄 · target_id 붙은 것 {with_id} · 근거 원문 따로 보관 "
          f"{sum(1 for b in rows if b.get('evidence'))}")
    if dumped:
        print(f"FAIL how가 원문 덤프다: {[b['what'] for b in dumped][:5]}")
        bad += 1

    total = sum(c["tokens"]["reclaim"] for c in items)
    inv_tot = INV.get("totals", {})
    file_side = sum(inv_tot.get(k, {}).get("tokens_est", 0) or 0
                    for k in ("rule", "skill", "command", "agent", "memory"))
    mcp_side = sum(v["tokens"] for v in MEAS_MCP.values())
    hook_side = sum(v["tokens"] for k, v in HOOKS.items() if k.startswith("hook:SessionStart:"))
    expect = file_side + mcp_side + hook_side
    diff = total - expect
    print(f"카드 {len(items)}장 · reclaim 합 {total:,}")
    print(f"  대조: 재고(enabled, 파일 기반) {file_side:,} + MCP 실측 {mcp_side:,} "
          f"+ 훅 출력 실측 {hook_side:,} = {expect:,} (차 {diff:+,}, {abs(diff)/expect:.0%})")
    if abs(diff) > expect * 0.15:
        print("  이유: 카드 합은 실측 행이 있으면 실측을 쓰고(스킬 목록 추정은 48% 과대), "
              "메모리 카드는 MEMORY.md 한 장만 담는다(프로젝트 CLAUDE.md·AGENTS.md는 카드가 없다). "
              "차가 그만큼 난다.")
    missing_meas = [c["id"] for c in items if c["tokens"].get("measured") is False]
    if missing_meas:
        print(f"  훅 미측정: {missing_meas}")
    print("--check ok" if not bad else f"--check FAILED ({bad})")
    return bad


def main() -> int:
    doc = {"generated_at": now(), "items": build_cards(),
           "hooks_measured": HOOKS, "grep_log": GREP_LOG}
    out = DATA / "decisions.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes, {len(doc['items'])} cards)")
    if "--check" in sys.argv:
        return check(doc)
    return 0


# cards.py is imported last, and on purpose: it reads the helpers above, while
# this file needs only its build_cards()/HOOKS at run time. The alias makes the
# `from decisions import ...` inside it find *this* module instead of loading a
# second copy of it (the script is __main__ when run directly).
sys.modules.setdefault("decisions", sys.modules[__name__])
from cards import HOOKS, build_cards  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
