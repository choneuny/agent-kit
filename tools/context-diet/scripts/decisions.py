#!/usr/bin/env python3
"""Build the decision cards — one card per handle the user can actually pull.

  uv run scripts/decisions.py            # -> data/decisions.json
  uv run scripts/decisions.py --check    # validate the file just written

Contract: docs/ledger/decision-cards.md ("데이터 계약"). Groups 1~8 are the
decision list in that document. Token numbers prefer the /context measurement
(data/context-measured.json); the calibrated estimate is the fallback.

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


PONYTAIL_HOOKS = HOME / ".claude/plugins/cache/ponytail/ponytail/4.8.4/hooks"
SUPERPOWERS = HOME / ".claude/plugins/cache/claude-plugins-official/superpowers/6.3.0"
SESSION_JSON = json.dumps({
    "session_id": "decisions-py-probe", "reason": "startup",
    "cwd": str(ROOT), "transcript_path": "", "hook_event_name": "SessionStart",
})


def measure_hooks() -> dict[str, dict]:
    """name -> {tokens, chars, measured, method, reason}"""
    m: dict[str, dict] = {}
    # 꺼진 플러그인의 훅은 세션에 안 실린다 — 세지 않는다
    enabled_plugins = json.loads((HOME / ".claude/settings.json").read_text(
        encoding="utf-8")).get("enabledPlugins", {})

    # 1. pseudo-honcho-context — pure reader (opens insights.jsonl, prints). Run it.
    ph = HOME / "workspace/claude-native/pseudo-honcho/bin/pseudo-honcho-context"
    out = run_capture([str(ph)], SESSION_JSON) if ph.is_file() else None
    tr = transcript_match("pseudo-honcho-context")
    if out is not None:
        m["hook:SessionStart:pseudo-honcho-context"] = {
            "chars": len(out), "tokens": est_text(out), "measured": True,
            "method": "실행(읽기 전용 스크립트)", "reason": None,
            "transcript_tokens": tr["tokens"] if tr else None,
        }
    elif tr:
        m["hook:SessionStart:pseudo-honcho-context"] = {
            "chars": tr["chars"], "tokens": tr["tokens"], "measured": True,
            "method": "트랜스크립트 주입 기록", "reason": None, "transcript_tokens": tr["tokens"]}
    else:
        m["hook:SessionStart:pseudo-honcho-context"] = {
            "chars": 0, "tokens": 0, "measured": False, "method": None,
            "reason": "스크립트도 트랜스크립트 기록도 못 찾았다"}

    # 2. the SessionStart health hook — appends to ndjson logs, mkdir/chmod, moves
    #    the refresh snapshot. Not read-only: measured off the transcript instead.
    tr = transcript_match("session-start-healthcheck")
    m["hook:SessionStart:healthcheck"] = (
        {"chars": tr["chars"], "tokens": tr["tokens"], "measured": True,
         "method": "트랜스크립트 주입 기록(실행 안 함 — 로그 파일에 쓴다)", "reason": None}
        if tr else
        {"chars": 0, "tokens": 0, "measured": False, "method": None,
         "reason": "로그 ndjson에 append·mkdir·chmod·스냅샷 이동이 있어 실행하지 않았고 트랜스크립트 기록도 없다"}
    )

    # 3. the PreCompact + SessionEnd hook — spawns a headless `claude -p` and writes
    #    files of its own. Never run from here.
    m["hook:PreCompact+SessionEnd:session-end-save"] = {
        "chars": 0, "tokens": 0, "measured": False, "method": None,
        "reason": "claude -p 자식 세션을 띄우고 저널·로그 파일을 쓴다 — 실행 금지. "
                  "출력은 사용자에게 가는 상태 메시지라 세션 컨텍스트에 실리지 않는다(트랜스크립트에 주입 기록 없음)",
    }

    # 4. ponytail SessionStart — the hook writes a flag file, but its output is
    #    getPonytailInstructions(mode); call that directly (read-only).
    tr = transcript_match("ponytail") or transcript_match("Loading ponytail")
    text = None
    instr = PONYTAIL_HOOKS / "ponytail-instructions.js"
    if instr.is_file():
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(
                f'const {{getPonytailInstructions}} = require({json.dumps(str(instr))});\n'
                'process.stdout.write(getPonytailInstructions("full"));\n'
            )
            probe = fh.name
        text = run_capture(["node", probe])
        try:
            os.unlink(probe)
        except OSError:
            pass
    if text:
        prefix = "PONYTAIL MODE ACTIVE — level: full\n\n"
        m["hook:SessionStart:ponytail"] = {
            "chars": len(prefix + text), "tokens": est_text(prefix + text), "measured": True,
            "method": "ponytail-instructions.js를 직접 호출(플래그 파일 쓰기 우회)", "reason": None,
            "transcript_tokens": tr["tokens"] if tr else None}
    elif tr:
        m["hook:SessionStart:ponytail"] = {
            "chars": tr["chars"], "tokens": tr["tokens"], "measured": True,
            "method": "트랜스크립트 주입 기록", "reason": None, "transcript_tokens": tr["tokens"]}
    else:
        m["hook:SessionStart:ponytail"] = {
            "chars": 0, "tokens": 0, "measured": False, "method": None,
            "reason": "node 실행 실패, 트랜스크립트 기록도 없다"}

    # ponytail SubagentStart injects the same block into every subagent.
    same = dict(m["hook:SessionStart:ponytail"])
    same["method"] = (same.get("method") or "") + " · SubagentStart도 같은 본문"
    m["hook:SubagentStart:ponytail"] = same

    # 5. superpowers SessionStart — cat + printf only. Run it.
    tr = transcript_match("run-hook.cmd")
    sp = SUPERPOWERS / "hooks/run-hook.cmd"
    out = None
    if sp.is_file():
        raw = run_capture(["bash", str(sp), "session-start"], SESSION_JSON,
                          cwd=str(SUPERPOWERS))
        # the script needs CLAUDE_PLUGIN_ROOT to pick the Claude Code envelope
        if raw is None or "hookSpecificOutput" not in (raw or ""):
            env_before = os.environ.get("CLAUDE_PLUGIN_ROOT")
            os.environ["CLAUDE_PLUGIN_ROOT"] = str(SUPERPOWERS)
            raw = run_capture(["bash", str(sp), "session-start"], SESSION_JSON, cwd=str(SUPERPOWERS))
            if env_before is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = env_before
        out = injected_from_stdout(raw) if raw else None
    if out:
        m["hook:SessionStart:superpowers"] = {
            "chars": len(out), "tokens": est_text(out), "measured": True,
            "method": "실행(cat+printf만 하는 읽기 전용 스크립트)", "reason": None,
            "transcript_tokens": tr["tokens"] if tr else None}
    elif tr:
        m["hook:SessionStart:superpowers"] = {
            "chars": tr["chars"], "tokens": tr["tokens"], "measured": True,
            "method": "트랜스크립트 주입 기록", "reason": None, "transcript_tokens": tr["tokens"]}
    else:
        m["hook:SessionStart:superpowers"] = {
            "chars": 0, "tokens": 0, "measured": False, "method": None,
            "reason": "실행 실패, 트랜스크립트 기록도 없다"}

    # 6. ponytail UserPromptSubmit — emits nothing unless the prompt starts with
    #    /ponytail, so its steady-state session cost is zero.
    m["hook:UserPromptSubmit:ponytail"] = {
        "chars": 0, "tokens": 0, "measured": True,
        "method": "본문 판독 — /ponytail 로 시작하는 프롬프트에만 출력한다",
        "reason": None}
    plugin_of = {"hook:SessionStart:superpowers": "superpowers@claude-plugins-official",
                 "hook:SessionStart:ponytail": "ponytail@ponytail",
                 "hook:SubagentStart:ponytail": "ponytail@ponytail",
                 "hook:UserPromptSubmit:ponytail": "ponytail@ponytail"}
    return {k: v for k, v in m.items()
            if enabled_plugins.get(plugin_of.get(k, ""), True) is not False}


HOOKS = measure_hooks()


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


def build_cards() -> list[dict]:
    cards: list[dict] = []

    # ── 1. notion MCP ─────────────────────────────────────────────────────────
    cards.append(mcp_card(
        "notion", 1,
        "notion MCP를 통째로 끌지, 쓰는 스킬 때문에 둘지",
        replacement="Notion 웹/앱에서 직접, 또는 필요할 때만 켠다"))

    # ── 2. hook output ────────────────────────────────────────────────────────
    hook_cards = [
        ("hook:SessionStart:pseudo-honcho-context",
         "세션 시작 훅이 넣는 사용자 사실 블록을 둘지",
         "~/.local/share/pseudo-honcho/insights.jsonl (정제본)",
         "필요할 때 파일을 직접 읽는다"),
        ("hook:SessionStart:healthcheck",
         "세션 시작 훅의 주입(훅 상태 배지 + /refresh 스냅샷)을 둘지",
         "~/.claude/scripts/session-start-healthcheck.sh", None),
        ("hook:PreCompact+SessionEnd:session-end-save",
         "세션 종료·압축 훅 등록 둘(PreCompact·SessionEnd)을 둘지",
         "~/.claude/scripts/session-end-save.sh", None),
    ]
    for hid, title, path, repl in hook_cards:
        h = HOOKS[hid]
        cards.append(card(
            id=hid, group=2, title=title, unit="훅 등록",
            tokens={"reclaim": h["tokens"],
                    "basis": "measured" if h["measured"] else "estimated",
                    "parts": [{"name": path, "tokens": h["tokens"]}],
                    "measured": h["measured"], "method": h.get("method"),
                    "reason": h.get("reason"), "output_chars": h["chars"]},
            usage=None,
            breaks=([brk("명령 learn-eval·save-session 자동 실행",
                         "이 훅이 세션 끝마다 headless claude로 두 명령을 돌린다 — 훅을 빼면 "
                         "세션 저널과 패턴 추출이 아무도 안 돌린다",
                         evidence="claude -p \"... run /learn-eval\" / \"... run /save-session\"",
                         target_id="command:learn-eval")]
                    if "session-end-save" in hid else
                    [brk("/refresh 스냅샷 인계",
                         "healthcheck가 /refresh가 남긴 refresh-snapshot.md를 읽어 다음 세션에 넣는다",
                         evidence="REFRESH_FILE=\"$STATE_DIR/refresh-snapshot.md\"",
                         target_id="command:refresh")]
                    if "healthcheck" in hid else []),
            replacement=repl,
            note=("측정값은 배지 한 줄뿐이다. /refresh 스냅샷이 대기 중이면 그 본문 전체가 "
                  "같은 훅으로 주입돼 훨씬 커진다 — 이 세션에는 대기분이 없었다"
                  if "healthcheck" in hid else None),
            verdicts=verdicts_for([i for i in ENABLED if i["kind"] == "hook"
                                   and Path(i["path"]).name in path]),
            options=["keep", "remove", "hold"], howto=HOWTO["hook"],
        ))

    # ── 3. MEMORY.md ──────────────────────────────────────────────────────────
    mem = next((i for i in ENABLED if i["kind"] == "memory" and i["name"].startswith("-home-")), None)
    if mem is None:
        print("no MEMORY.md item in inventory; skipping memory card", file=sys.stderr)
    else:
        t, basis = item_tokens(mem)
        body = read_text(mem["path"])
        lines = [l for l in body.splitlines() if l.strip().startswith("- ")]
        cards.append(card(
            id="memory:MEMORY.md", group=3,
            title=f"메모리 색인 {len(lines)}줄 중 무엇을 지울지", unit="메모리 파일",
            tokens={"reclaim": t, "basis": basis,
                    "parts": [{"name": f"{len(lines)}줄 색인", "tokens": t}]},
            usage=None,
            breaks=[brk("졸업한 프로젝트 포인터",
                        "졸업 표시 줄을 지우면 옛 프로젝트가 어느 repo로 갔는지를 다음 세션이 다시 찾는다",
                        target_id=f"memory:{mem['name']}")],
            replacement="프로젝트 전용 메모리 디렉터리와 repo 문서",
            verdicts=verdicts_for([mem]),
            options=["keep", "shrink", "hold"], howto=HOWTO["memory"],
            note=f"본문: {mem['path']}",
        ))


    # ── 4. local dirs ─────────────────────────────────────────────────────────
    cmd_breaks = []
    ses = HOME / ".claude/scripts/session-end-save.sh"
    txt = read_text(ses)
    for name in ("learn-eval", "save-session"):
        if f"/{name}" in txt:
            line = next(l.strip() for l in txt.splitlines() if f"/{name}" in l)
            cmd_breaks.append(brk(
                f"훅 {ses.name}이 /{name}을 부른다",
                f"세션이 끝나거나 압축될 때 훅이 headless claude 세션을 띄워 /{name}을 돌린다 — "
                f"사람이 부르는 명령이 아니다",
                evidence=line[:200], target_id=f"command:{name}"))
    GREP_LOG.append({"label": "dir:command", "pattern": "/learn-eval|/save-session",
                     "files": 1, "hits": len(cmd_breaks)})
    hc_path = HOME / ".claude/scripts/session-start-healthcheck.sh"
    hc = read_text(hc_path)
    if "refresh-snapshot" in hc:
        cmd_breaks.append(brk(
            f"훅 {hc_path.name}이 /refresh 산출물을 읽는다",
            "/refresh가 남긴 스냅샷 파일을 세션 시작 훅이 읽어 다음 세션에 주입한다 — "
            "명령을 빼면 그 인계가 끊긴다",
            evidence='REFRESH_FILE="$STATE_DIR/refresh-snapshot.md"',
            target_id="command:refresh"))

    cards.append(dir_card("skill", [str(HOME / ".agents/skills"), str(HOME / ".claude/skills")], 4,
                          "개인 스킬 디렉터리 — ECC 잔재를 걷고 쓰는 것만 남길지"))
    cards.append(dir_card("agent", [str(HOME / ".claude/agents")], 4,
                          "로컬 에이전트 디렉터리 — 디렉터리째 걷을지"))
    cards.append(dir_card("command", [str(HOME / ".claude/commands")], 4,
                          "로컬 슬래시 명령 디렉터리 — ECC 50여 개를 걷을지",
                          extra_breaks=cmd_breaks))

    # ── 5. rules ──────────────────────────────────────────────────────────────
    rules = inv_of("rule", lambda i: True)
    by_verdict: dict[str, list[dict]] = {}
    for r in rules:
        j = JUDG.get(("rule", r["name"]))
        by_verdict.setdefault(j["verdict"] if j else "Keep", []).append(r)

    for r in sorted(by_verdict.get("Merge", []), key=lambda r: r["name"]):
        j = JUDG[("rule", r["name"])]
        t, basis = item_tokens(r)
        cards.append(card(
            id=f"rule:{r['name']}", group=5,
            title=f"규칙 {r['name']}을 {j['merge_into']}에 합칠지", unit="규칙 파일",
            tokens={"reclaim": t, "basis": basis, "parts": [{"name": r["name"], "tokens": t}]},
            usage=None, breaks=[], replacement=f"{j['merge_into']} 한 문서로",
            verdicts=verdicts_for([r]), pair=rule_pair(r["name"], j["merge_into"]),
            options=["keep", f"merge:{j['merge_into']}", "shrink", "hold"],
            howto=HOWTO["rule"], note=SUMM.get(("rule", r["name"])),
        ))

    for verdict in ("Improve", "Update", "Retire"):
        for r in sorted(by_verdict.get(verdict, []), key=lambda r: r["name"]):
            t, basis = item_tokens(r)
            verb = {"Improve": "줄일지", "Update": "손볼지", "Retire": "뺄지"}[verdict]
            cards.append(card(
                id=f"rule:{r['name']}", group=5,
                title=f"규칙 {r['name']}({t:,} 토큰)을 {verb}", unit="규칙 파일",
                tokens={"reclaim": t, "basis": basis, "parts": [{"name": r["name"], "tokens": t}]},
                usage=None, breaks=[], replacement=None, verdicts=verdicts_for([r]),
                options=["keep", "shrink", "remove", "hold"], howto=HOWTO["rule"],
                note=(SUMM.get(("rule", r["name"]))
                      or ("본문이 비어 있다 — 회수할 토큰이 없고 파일만 남았다" if not t else None)),
            ))

    keeps = sorted(by_verdict.get("Keep", []), key=lambda r: r["name"])
    if keeps:
        parts, total = [], 0
        for r in keeps:
            t, _ = item_tokens(r)
            parts.append({"name": r["name"], "tokens": t})
            total += t
        parts.sort(key=lambda p: -p["tokens"])
        cards.append(card(
            id="rule:keep-as-is", group=5,
            title=f"그대로 두는 규칙 {len(keeps)}개 — 정말 그대로 둘지",
            unit="규칙 파일",
            tokens={"reclaim": total, "basis": "measured", "parts": parts},
            usage=None, verdicts=verdicts_for(keeps),
            options=["keep", "shrink", "hold"], howto=HOWTO["rule"],
        ))

    # ── 6. the other MCP servers ──────────────────────────────────────────────
    cards.append(mcp_card("filesystem", 6, "filesystem MCP를 켜 둘지",
                          replacement="내장 Read·Write·Edit·Bash 도구"))
    cards.append(mcp_card("context7", 6, "context7 MCP를 켜 둘지",
                          replacement="WebFetch로 공식 문서 직접 읽기"))
    for name, title in (("canvas-lms", "canvas-lms MCP(26S-AIP 프로젝트 전용)를 켜 둘지"),
                        ("caveman-shrink", "caveman-shrink MCP(26S-AIP 프로젝트 전용)를 켜 둘지")):
        c = mcp_card(name, 6, title)
        if not c["tokens"]["reclaim"]:
            c["tokens"]["basis"] = "estimated"
            c["note"] = ((c.get("note") or "") +
                         " · 이 세션에서는 안 실린다 — /context 실측에 행이 없다")
        cards.append(c)

    # ── 7. plugins ────────────────────────────────────────────────────────────
    plugin_hook = {
        "superpowers@claude-plugins-official": ["hook:SessionStart:superpowers"],
        "ponytail@ponytail": ["hook:SessionStart:ponytail", "hook:SubagentStart:ponytail",
                              "hook:UserPromptSubmit:ponytail"],
    }
    plugins = sorted({i["plugin"] for i in ENABLED if i.get("plugin")})
    for pl in plugins:
        items = [i for i in ENABLED if i.get("plugin") == pl]
        parts, total, basis = [], 0, "measured"
        for i in sorted(items, key=lambda i: i["name"]):
            t, b = item_tokens(i)
            if b != "measured":
                basis = "mixed"
            parts.append({"name": f"{i['kind']} {i['name']}", "tokens": t})
            total += t
        breaks = []
        for hid in plugin_hook.get(pl, []):
            h = HOOKS[hid]
            # Only the main-session injection is part of this session's bill.
            # SubagentStart repeats the same block per subagent; UserPromptSubmit
            # emits nothing unless the prompt is a /ponytail command.
            counts = hid.startswith("hook:SessionStart:")
            parts.append({"name": f"{hid} (훅 출력{'' if counts else ', 세션 합계 밖'})",
                          "tokens": h["tokens"] if counts else 0})
            if counts:
                total += h["tokens"]
            if h["tokens"]:
                scope = "세션마다" if counts else "서브에이전트마다 따로"
                breaks.append(brk(hid, f"{scope} {h['tokens']:,} 토큰을 주입한다",
                                  evidence=h["method"], target_id=hid))
        parts.sort(key=lambda p: -p["tokens"])
        short = pl.split("@")[0]
        cards.append(card(
            id=f"plugin:{short}", group=7,
            title=f"플러그인 {short}을 통째로 둘지", unit="플러그인",
            tokens={"reclaim": total, "basis": basis, "parts": parts},
            usage=usage_for([(i["kind"], i["name"]) for i in items]),
            breaks=breaks, replacement=None, verdicts=verdicts_for(items),
            options=["keep", "remove", "hold"], howto=HOWTO["plugin"],
            note=f"enabledPlugins 키: {pl}",
        ))

    # ── 8. built-ins and app connectors ───────────────────────────────────────
    builtin_servers = ["claude-in-chrome", "ccd_session", "ccd_session_mgmt",
                       "mcp-registry", "scheduled-tasks", "visualize"]
    parts = [{"name": s, "tokens": MEAS_MCP.get(s, {}).get("tokens", 0)} for s in builtin_servers]
    parts.sort(key=lambda p: -p["tokens"])
    cards.append(card(
        id="builtin:mcp", group=8,
        title="내장 MCP 여섯 — 여기서 결정할 게 없다", unit="내장 MCP",
        tokens={"reclaim": sum(p["tokens"] for p in parts), "basis": "measured", "parts": parts},
        usage=None, breaks=[], replacement=None,
        verdicts=verdicts_for([{"kind": "mcp", "name": s} for s in builtin_servers]),
        options=[], howto=HOWTO["builtin"],
        note="어느 설정 파일에도 없다 — /context 실측으로만 잡힌다",
    ))
    connectors = [s for s in MEAS_MCP if re.fullmatch(r"[0-9a-f-]{36}", s)]
    parts = [{"name": s, "tokens": MEAS_MCP[s]["tokens"]} for s in sorted(connectors)]
    cards.append(card(
        id="connector:app", group=8,
        title=f"앱 커넥터 {len(parts)}개 — 앱 설정에서 뺀다", unit="앱 커넥터",
        tokens={"reclaim": sum(p["tokens"] for p in parts), "basis": "measured", "parts": parts},
        usage=None, breaks=[], replacement=None, verdicts=[],
        options=[], howto=HOWTO["connector"],
        note="UUID 이름의 서버 = claude.ai 앱에서 연결한 커넥터(Google Drive·Canvas 등)",
    ))
    return cards


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
    hook_side = sum(HOOKS[k]["tokens"] for k in
                    ("hook:SessionStart:pseudo-honcho-context", "hook:SessionStart:healthcheck",
                     "hook:SessionStart:ponytail", "hook:SessionStart:superpowers"))
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


if __name__ == "__main__":
    sys.exit(main())
