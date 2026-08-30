#!/usr/bin/env python3
"""Build the context map — the whole session context as one tree.

  uv run scripts/map.py            # -> data/map.json
  uv run scripts/map.py --check    # + reconcile layer sums against /context

Contract: docs/ledger/context-map.md ("데이터 계약"). Layers follow the
/context categories; under each layer sit units (server, directory, plugin,
file group) and under those the items. Node ids join with decisions.json
(unit_id), judgments.json and summaries.json (id).

Resident tokens prefer the /context measurement; the calibrated file estimate
is the fallback (basis says which). Hook output is measured, not estimated —
those numbers are reused from decisions.json (see decision-cards.md).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HOME = Path.home()

# MCP servers whose tools are loaded up front; everything else is deferred
# (this session's tool list: only these two appear without ToolSearch).
EAGER_MCP = {"ccd_session", "visualize"}
# Servers we configured ourselves (~/.claude.json). Built-ins and the UUID-named
# app connectors are not in any settings file.
OURS_MCP = {"notion", "filesystem", "context7", "canvas-lms", "caveman-shrink"}

# How much an installed_at can be trusted. transcript-first is the day the name
# was first *used*, not installed — the UI's "새로 들어옴(보류)" must not lean on it.
CONFIDENCE = {"plugin-meta": "high", "agents-git": "high",
              "birth-time": "medium", "transcript-first": "low"}

BODY_OUTLIER_RATIO = 20
BODY_OUTLIER_ABS = 3000


def load(name: str) -> dict:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


INV = load("inventory.json")
ITEMS = INV.get("items", [])
ENABLED = [i for i in ITEMS if i.get("enabled")]
BY_KIND_NAME = {(i["kind"], i["name"]): i for i in ITEMS}
MEAS = load("context-measured.json")
CAT = MEAS.get("categories", {})
DEC = load("decisions.json")
JUDG = {(i["kind"], i["name"]): i for i in load("judgments.json").get("items", [])}
_SUMM_ITEMS = load("summaries.json").get("items", [])
SUMM = {(i["kind"], i["name"]): i.get("summary") for i in _SUMM_ITEMS}
# 이름만으로는 갈리지 않는 것들이 있다(rules/<언어>/review.md 열 개) — 경로가 있으면 경로로.
SUMM_PATH = {i["path"]: i.get("summary") for i in _SUMM_ITEMS if i.get("path")}
USAGE = {(i["kind"], i["name"]): i for i in load("usage.json").get("items", [])}
_INS_ITEMS = load("installed.json").get("items", [])
INSTALLED = {(i["kind"], i["name"]): i for i in _INS_ITEMS}
INSTALLED_PATH = {i["path"]: i for i in _INS_ITEMS if i.get("path")}


def actions() -> list[dict]:
    p = DATA / "actions.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


ACTIONS = actions()
REMOVED = {r["id"] for r in ACTIONS if r.get("choice") == "remove"}
LAST_ACTION_AT = max((r["at"] for r in ACTIONS if r.get("at")), default=None)
INV_KNOWN = {(i["kind"], i["name"]) for i in ITEMS}
INV_ENABLED = {(i["kind"], i["name"]) for i in ENABLED}
INV_PATH_ENABLED = {i["path"] for i in ENABLED if i.get("path")}
# 표본을 뜬 시각(초 단위) — 같은 보정 실행이 남긴다. 이보다 새 파일의 실측은 낡은 값이다.
SAMPLE_AT = load("calibration.json").get("measured_at") or ""
MEAS_SKILLS = {s["name"] for s in MEAS.get("skills", [])}
MEAS_AGENTS = {a["name"] for a in MEAS.get("agents", [])}


def dropped(name: str, *kinds: str) -> bool:
    """실측 표본에는 남아 있지만 지금은 없는 항목.

    빠진 길이 둘이다 — actions.jsonl에 remove로 적힌 것(끈 에이전트·명령은 재고 스캔
    범위 밖으로 옮겨져 재고에서도 사라진다)과, 재고에 있으면서 enabled:false인 것.
    재고에도 actions에도 없으면 내장·플러그인이니 measured-only로 남긴다.
    """
    if f"plugin:{name.split(':')[0]}" in REMOVED:
        return True  # 꺼진 플러그인 소속(superpowers:*, anthropic-skills:* 류)
    return any(f"{k}:{name}" in REMOVED or ((k, name) in INV_KNOWN and (k, name) not in INV_ENABLED)
               for k in kinds)


def cat(name: str) -> int:
    return CAT.get(name, {}).get("tokens", 0)


def usage_of(kind: str, name: str) -> dict | None:
    u = USAGE.get((kind, name))
    if not u:
        return None
    out = {"calls_30d": u["calls_30d"], "calls_7d": u["calls_7d"], "last_used": u.get("last_used")}
    if u.get("by_30d"):
        out["by_30d"] = u["by_30d"]
    return out


def node(id: str, name: str, kind: str, tokens: int, *, basis: str = "measured",
         body_tokens: int | None = None, fixed: bool = False, unit_id: str | None = None,
         path: str | None = None, children: list | None = None, note: str | None = None,
         judge_key: tuple[str, str] | None = None, usage_key: tuple[str, str] | None = None,
         deferred: bool = False) -> dict:
    j = JUDG.get(judge_key) if judge_key else None
    n = {
        "id": id, "name": name, "kind": kind,
        "tokens": tokens, "basis": basis,
        "body_tokens": body_tokens if body_tokens is not None else tokens,
        "fixed": fixed,
        "usage": usage_of(*usage_key) if usage_key else None,
        "installed_at": None, "installed_source": None, "installed_confidence": None,
        "verdict": j["verdict"] if j else None,
        "merge_into": j.get("merge_into") if j else None,
        "reason": j.get("reason") if j else None,
        "summary": SUMM_PATH.get(path) or (SUMM.get(judge_key) if judge_key else None),
        "unit_id": unit_id,
        "path": path,
        "flags": [],
        "note": note,
    }
    if deferred:
        n["deferred"] = True
    ins = INSTALLED_PATH.get(path) or (INSTALLED.get(judge_key) if judge_key else None)
    # Nothing can be turned off here, so "arrived recently" is not a decision the
    # user makes about it — leave the date empty rather than let the UI hold it.
    if ins and not fixed:
        n["installed_at"] = ins.get("installed_at")
        n["installed_source"] = ins.get("source")
        n["installed_confidence"] = CONFIDENCE.get(ins.get("source"))
    # body outlier: a listing line of 50 tokens hiding a 5k body
    b, t = n["body_tokens"], n["tokens"]
    if b and t and b != t and (b > t * BODY_OUTLIER_RATIO or b > BODY_OUTLIER_ABS):
        n["flags"].append("body_outlier")
    if children is not None:
        n["children"] = children
    return n


def group(id: str, name: str, kind: str, children: list, *, fixed: bool = False,
          note: str | None = None, unit_id: str | None = None) -> dict:
    tokens = sum(c["tokens"] for c in children)
    body = sum(c["body_tokens"] for c in children)
    bases = {c["basis"] for c in children}
    n = node(id, name, kind, tokens,
             basis="measured" if bases == {"measured"} else ("estimated" if bases == {"estimated"} else "mixed"),
             body_tokens=body, fixed=fixed, note=note, unit_id=unit_id, children=children)
    n["flags"] = []
    return n


# ── layers ────────────────────────────────────────────────────────────────────
def layer_system_prompt() -> dict:
    return group("layer:system-prompt", "시스템 프롬프트", "layer", [
        node("system:prompt", "시스템 프롬프트", "system", cat("System prompt"), fixed=True,
             note="하네스가 싣는 본문 — 끌 수 없고 내역도 안 보인다"),
    ], fixed=True)


def layer_system_tools() -> dict:
    return group("layer:system-tools", "시스템 도구", "layer", [
        node("system:tools", "시스템 도구(상주)", "system", cat("System tools"), fixed=True),
        node("system:tools-deferred", "시스템 도구(지연 로드)", "system",
             cat("System tools (deferred)"), fixed=True, deferred=True,
             note="ToolSearch로 불러야 스키마가 실린다 — /context 총합 밖"),
    ], fixed=True)


def layer_mcp() -> dict:
    by_server = MEAS.get("mcp", {}).get("by_server", {})
    tools = MEAS.get("mcp", {}).get("tools", [])
    units: dict[str, list] = {"ours": [], "builtin": [], "connector": []}
    for server, meas in sorted(by_server.items(), key=lambda kv: -kv[1]["tokens"]):
        if dropped(server, "mcp"):
            continue  # 실행으로 뺀 서버 — 옛 /context 표본에는 남아 있다
        if len(server) == 36 and server.count("-") == 4:
            bucket, unit_id, fixed = "connector", "connector:app", True
        elif server in OURS_MCP:
            bucket, unit_id, fixed = "ours", f"mcp:{server}", False
        else:
            bucket, unit_id, fixed = "builtin", "builtin:mcp", True
        kids = [
            node(f"mcp_tool:{server}:{t['name'].split('__')[-1]}",
                 t["name"].split("__")[-1], "mcp_tool", t["tokens"],
                 fixed=fixed, unit_id=unit_id,
                 judge_key=("mcp_tool", t["name"]), usage_key=("mcp_tool", t["name"]),
                 deferred=server not in EAGER_MCP)
            for t in sorted((t for t in tools if t["server"] == server),
                            key=lambda t: -t["tokens"])]
        server_node = node(
            f"mcp:{server}", server, "mcp", meas["tokens"], unit_id=unit_id, fixed=fixed,
            judge_key=("mcp", server), usage_key=("mcp", server),
            deferred=server not in EAGER_MCP, children=kids,
            note=f"도구 {n_tools}개" if (n_tools := len(kids)) else "이 세션에 실린 도구가 없다",
            path=str(HOME / ".claude.json") if bucket == "ours" else None)
        units[bucket].append(server_node)
    # our servers that this session did not load (project-scoped ones)
    for server in sorted(OURS_MCP - set(by_server)):
        units["ours"].append(node(
            f"mcp:{server}", server, "mcp", 0, basis="estimated", unit_id=f"mcp:{server}",
            judge_key=("mcp", server), usage_key=("mcp", server),
            note="이 세션(sketches)에서는 안 실린다 — /context 실측에 행이 없다"))
    return group("layer:mcp", "MCP 도구", "layer", [
        group("unit:mcp-ours", "우리가 설정한 서버", "unit", units["ours"]),
        group("unit:mcp-builtin", "하네스 내장 서버", "unit", units["builtin"], fixed=True,
              unit_id="builtin:mcp", note="어느 설정 파일에도 없다 — /context 실측으로만 잡힌다"),
        group("unit:mcp-connector", "앱 커넥터", "unit", units["connector"], fixed=True,
              unit_id="connector:app", note="claude.ai 앱에서 연결한 커넥터 — 앱 설정에서만 뺀다"),
    ])


def memory_label(path: str, kind: str, name: str) -> str:
    """Human name for a memory row — the id keeps the slug, the screen does not."""
    if kind != "memory":
        return name
    q = Path(path)
    if q.name == "MEMORY.md":           # ~/.claude/projects/<slug>/memory/MEMORY.md
        return f"MEMORY.md ({q.parent.parent.name.rstrip('-').split('-')[-1]})"
    return f"{q.parent.name}/{q.name}"  # sketches/AGENTS.md


def layer_memory() -> dict:
    rules, project, auto = [], [], []
    for m in MEAS.get("memory_files", []):
        path, tok = m["path"], m["tokens"]
        inv = next((i for i in ITEMS if i["path"] == path), None)
        kind = inv["kind"] if inv else ("rule" if "/rules/" in path else "memory")
        name = inv["name"] if inv else Path(path).stem
        # 규칙은 common만 상주한다 — 지운 규칙과 `paths:` 규칙은 옛 표본에만 남아 있다
        if kind == "rule" and path not in INV_PATH_ENABLED:
            continue
        if kind != "rule" and inv and not inv.get("enabled"):
            continue
        # 표본 이후 바뀐 파일은 실측이 낡았다 — 파일 추정으로 갈아탄다
        changed = inv and SAMPLE_AT and (inv.get("mtime") or "") > SAMPLE_AT
        if changed:
            tok = inv["tokens_est"] or tok
        n = node(f"{kind}:{name}", memory_label(path, kind, name), kind, tok, path=path,
                 basis="estimated" if changed else "measured",
                 judge_key=(kind, name), usage_key=(kind, name),
                 note="실측 뒤 파일이 바뀌었다 — 파일 추정값이다" if changed else None)
        if kind == "rule":
            n["unit_id"] = f"rule:{name}" if JUDG.get(("rule", name), {}).get("verdict") in (
                "Merge", "Improve", "Update", "Retire") else "rule:keep-as-is"
            rules.append(n)
        elif m["type"] == "AutoMem" or "/memory/MEMORY.md" in path:
            n["unit_id"] = "memory:MEMORY.md(sketches)"
            auto.append(n)
        else:
            project.append(n)
    # 실측 뒤에 들어온 상주 규칙 — 재고에만 있고 표본 행이 없다 (스킬 층과 같은 갈래)
    meas_paths = {m["path"] for m in MEAS.get("memory_files", [])}
    for i in ENABLED:
        if i["kind"] != "rule" or i["path"] in meas_paths or not i.get("tokens_est"):
            continue
        n = node(f"rule:{i['name']}", i["name"], "rule", i["tokens_est"] or 0,
                 basis="estimated", path=i["path"], judge_key=("rule", i["name"]),
                 usage_key=("rule", i["name"]),
                 note="실측 표본 뒤에 들어왔다 — 파일 추정값이다")
        n["unit_id"] = f"rule:{i['name']}" if JUDG.get(("rule", i["name"]), {}).get(
            "verdict") in ("Merge", "Improve", "Update", "Retire") else "rule:keep-as-is"
        rules.append(n)
    paths_rules = [
        node(f"rule:{Path(i['path']).parent.name}/{i['name']}",
             f"{Path(i['path']).parent.name}/{i['name']}", "rule", i["tokens_est"] or 0,
             basis="estimated", path=i["path"], deferred=True, unit_id="rule:paths",
             judge_key=("rule", i["name"]), usage_key=("rule", i["name"]),
             note="`paths:` 규칙 — 맞는 파일을 건드릴 때만 실린다")
        for i in ITEMS
        if i["kind"] == "rule" and not i.get("enabled") and i.get("tokens_est")
    ]
    for lst in (rules, project, auto, paths_rules):
        lst.sort(key=lambda n: -n["tokens"])
    return group("layer:memory", "메모리 파일", "layer", [
        group("unit:rules", "규칙 (~/.agents/rules/common)", "unit", rules),
        group("unit:rules-paths", "규칙 (경로로 걸리는 것 — 지연)", "unit", paths_rules,
              unit_id="rule:paths",
              note="세션 시작에는 안 실린다 — /context 실측이 없어 파일 추정값이다"),
        group("unit:project-files", "프로젝트 CLAUDE.md·AGENTS.md", "unit", project,
              note="끄지 못한다 — 본문을 줄이는 수밖에 없다"),
        group("unit:auto-memory", "프로젝트 메모리 색인 MEMORY.md", "unit", auto,
              unit_id="memory:MEMORY.md(sketches)"),
    ])


def layer_skills() -> dict:
    personal, commands, builtin = [], [], []
    plugins: dict[str, list] = {}
    for s in MEAS.get("skills", []):
        name, tok, src = s["name"], s["tokens"], s["source"]
        approx = s.get("approx") or s.get("upper_bound")
        if dropped(name, "skill", "command"):
            continue  # 오늘 끈 명령·스킬 — 옛 /context 표본에는 남아 있다
        inv = BY_KIND_NAME.get(("skill", name)) or BY_KIND_NAME.get(("command", name))
        kind = inv["kind"] if inv else "skill"
        body = (inv or {}).get("tokens_body_est") or tok
        n = node(f"{kind}:{name}", name, kind, tok, basis="measured",
                 body_tokens=body, path=(inv or {}).get("path"),
                 judge_key=(kind, name), usage_key=(kind, name),
                 note="/context 표기가 `~`·`< 20` 근사다 — 상한으로 읽는다" if approx else None)
        if src == "Built-in":
            n["fixed"] = True
            builtin.append(n)
        elif src.startswith("Plugin ("):
            short = src[len("Plugin ("):-1]
            n["unit_id"] = f"plugin:{short}"
            plugins.setdefault(short, []).append(n)
        elif kind == "command":
            n["unit_id"] = "dir:command"
            commands.append(n)
        else:
            n["unit_id"] = "dir:skill"
            personal.append(n)
    # 실측 뒤에 들어온 것 — 재고에만 있고 /context 행이 없다
    for i in ENABLED:
        if i["kind"] not in ("skill", "command") or i["name"] in MEAS_SKILLS:
            continue
        n = node(f"{i['kind']}:{i['name']}", i["name"], i["kind"], i["tokens_est"] or 0,
                 basis="estimated", body_tokens=i.get("tokens_body_est") or i["tokens_est"],
                 path=i["path"], judge_key=(i["kind"], i["name"]),
                 usage_key=(i["kind"], i["name"]),
                 note="실측 표본 뒤에 들어왔다 — 파일 추정값이다")
        n["unit_id"] = "dir:command" if i["kind"] == "command" else "dir:skill"
        (commands if i["kind"] == "command" else personal).append(n)
    for lst in [personal, commands, builtin, *plugins.values()]:
        lst.sort(key=lambda n: -n["tokens"])
    units = [
        group("unit:skills-personal", "개인 스킬 (~/.agents/skills)", "unit", personal,
              unit_id="dir:skill"),
        group("unit:commands", "로컬 슬래시 명령 (~/.claude/commands)", "unit", commands,
              unit_id="dir:command"),
        group("unit:skills-builtin", "Built-in 스킬", "unit", builtin, fixed=True,
              note="하네스가 싣는다 — 끌 수 없다"),
    ]
    units += [group(f"unit:skills-plugin:{p}", f"플러그인 {p}", "unit", ns, unit_id=f"plugin:{p}")
              for p, ns in sorted(plugins.items(), key=lambda kv: -sum(n["tokens"] for n in kv[1]))]
    return group("layer:skills", "스킬 목록", "layer", units,
                 note="목록 한 줄만 상주한다 — 본문은 호출할 때 실린다(body_tokens)")


def layer_agents() -> dict:
    local, plugins = [], {}
    for a in MEAS.get("agents", []):
        name, tok = a["name"], a["tokens"]
        if dropped(name, "agent"):
            continue  # 오늘 agents-disabled로 옮긴 에이전트
        inv = BY_KIND_NAME.get(("agent", name))
        n = node(f"agent:{name}", name, "agent", tok,
                 body_tokens=(inv or {}).get("tokens_body_est") or tok,
                 path=(inv or {}).get("path"),
                 judge_key=("agent", name), usage_key=("agent", name))
        if a["source"] == "Plugin" and ":" in name:
            short = name.split(":", 1)[0]
            n["unit_id"] = f"plugin:{short}"
            plugins.setdefault(short, []).append(n)
        else:
            n["unit_id"] = "dir:agent"
            local.append(n)
    for i in ENABLED:
        if i["kind"] != "agent" or i["name"] in MEAS_AGENTS:
            continue
        local.append(node(f"agent:{i['name']}", i["name"], "agent", i["tokens_est"] or 0,
                          basis="estimated", body_tokens=i.get("tokens_body_est"),
                          path=i["path"], unit_id="dir:agent",
                          judge_key=("agent", i["name"]), usage_key=("agent", i["name"]),
                          note="실측 표본 뒤에 들어왔다 — 파일 추정값이다"))
    local.sort(key=lambda n: -n["tokens"])
    units = [group("unit:agents-local", "로컬 에이전트 (~/.claude/agents)", "unit", local,
                   unit_id="dir:agent")]
    units += [group(f"unit:agents-plugin:{p}", f"플러그인 {p} 에이전트", "unit",
                    sorted(ns, key=lambda n: -n["tokens"]), unit_id=f"plugin:{p}")
              for p, ns in sorted(plugins.items())]
    return group("layer:agents", "커스텀 에이전트", "layer", units)


# hook id in decisions.json -> (judgments key, does it land in this session's context)
HOOK_JUDGE = {
    "hook:SessionStart:pseudo-honcho-context": ("hook", "SessionStart:pseudo-honcho-context"),
    "hook:SessionStart:healthcheck": ("hook", "SessionStart:session-start-healthcheck.sh"),
    "hook:PreCompact+SessionEnd:session-end-save": ("hook", "SessionEnd:session-end-save.sh"),
    "hook:SessionStart:ponytail": ("hook", "ponytail:SessionStart"),
    "hook:SubagentStart:ponytail": ("hook", "ponytail:SubagentStart"),
    "hook:UserPromptSubmit:ponytail": ("hook", "ponytail:UserPromptSubmit"),
    "hook:SessionStart:superpowers": ("hook", "SessionStart:superpowers"),
}


def layer_hooks() -> dict:
    kids = []
    for hid, h in DEC.get("hooks_measured", {}).items():
        counts = hid.startswith("hook:SessionStart:")
        note = h.get("method") or h.get("reason")
        if not counts:
            note = (note or "") + " · 세션 합계 밖(서브에이전트마다 따로 / 컨텍스트에 안 실림)"
        kids.append(node(
            hid, hid.split(":", 1)[1], "hook", h["tokens"] if counts else 0,
            basis="measured" if h["measured"] else "estimated",
            body_tokens=h["tokens"], unit_id=hid, note=note,
            judge_key=HOOK_JUDGE.get(hid)))
    kids.sort(key=lambda n: -n["tokens"])
    return group("layer:hooks", "훅 출력", "layer", kids,
                 note="/context 범주에 없다 — 훅 주입은 Messages로 들어간다. 층 합계는 설정 부분 대조에서 뺀다")


LAYERS = [layer_system_prompt, layer_system_tools, layer_mcp,
          layer_memory, layer_skills, layer_agents, layer_hooks]


def measured_at() -> str | None:
    """/context 표본을 뜬 날 — 파일 이름 앞머리(2026-08-22-fable-cli.md)가 유일한 날짜다."""
    src = MEAS.get("source_file")
    stem = Path(src).name[:10] if src else ""
    return stem if len(stem) == 10 and stem[4] == stem[7] == "-" else None


def build() -> dict:
    layers = [f() for f in LAYERS]
    root = group("root", "세션 컨텍스트", "root", layers)
    root["note"] = "Messages·Compact buffer·Free space는 설정이 아니므로 지도에 없다"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "context_sample": MEAS.get("source_file"),
            "measured_at": measured_at(),
            "stale_since": LAST_ACTION_AT,
            "context_total_tokens": MEAS.get("total_tokens"),
            "inventory_at": INV.get("generated_at"),
            "decisions_at": DEC.get("generated_at"),
            "installed": bool(INSTALLED),
        },
        "notes": [
            "MCP 도구 결과 크기(호출마다 돌아오는 본문)는 재지 않았다 — 주 축은 상주 토큰이다",
            "스킬 행의 /context 값은 `~`·`< 20` 근사라 상한으로 읽는다",
        ],
        "root": root,
    }


# ── check ─────────────────────────────────────────────────────────────────────
# 층 -> (상주 범주, 지연 범주). 메모리 층의 `paths:` 규칙은 /context에 범주가 없다 —
# 지연 칸에 지도 값만 서고 대조 상대가 없다.
LAYER_TO_CAT = {
    "layer:system-prompt": (["System prompt"], []),
    "layer:system-tools": (["System tools"], ["System tools (deferred)"]),
    "layer:mcp": (["MCP tools"], ["MCP tools (deferred)"]),
    "layer:memory": (["Memory files"], []),
    "layer:skills": (["Skills"], []),
    "layer:agents": (["Custom agents"], []),
}


def walk(n):
    yield n
    for c in n.get("children", []):
        yield from walk(c)


def check(doc: dict) -> int:
    root = doc["root"]
    nodes = list(walk(root))
    bad = 0
    ids = [n["id"] for n in nodes]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        print(f"FAIL 중복 id: {dupes[:10]}")
        bad += 1
    for n in nodes:
        if "children" in n:
            s = sum(c["tokens"] for c in n["children"])
            if s != n["tokens"]:
                print(f"FAIL 합계 불일치: {n['id']} {n['tokens']} != 자식합 {s}")
                bad += 1

    def deferred_sum(n):
        if n.get("deferred"):
            return n["tokens"]
        return sum(deferred_sum(c) for c in n.get("children", []))

    print(f"{'층':32} {'지도(상주)':>11} {'/context':>9} {'차':>8} {'지연':>9}")
    total_map = total_cat = 0
    for layer in root["children"]:
        pair = LAYER_TO_CAT.get(layer["id"])
        lazy = deferred_sum(layer)
        m = layer["tokens"] - lazy
        if pair:
            c = sum(cat(x) for x in pair[0])
            total_map += m
            total_cat += c
            print(f"{layer['name']:32} {m:11,} {c:9,} {m - c:+8,} {lazy:9,}")
        else:
            print(f"{layer['name']:32} {m:11,} {'—':>9} {'대조 밖':>8} {lazy:9,}")
    print(f"{'설정 부분 합':32} {total_map:11,} {total_cat:9,} {total_map - total_cat:+8,}")

    total = MEAS.get("total_tokens", 0)
    resident = total_cat
    if doc["source"].get("stale_since", "") > (doc["source"].get("measured_at") or ""):
        print(f"\n주의: /context 표본은 {doc['source']['measured_at']}인데 하네스는 "
              f"{doc['source']['stale_since'][:10]}까지 바뀌었다 — 새 표본을 뜨기 전까지 "
              f"남은 항목의 값은 그 날의 실측이다")
    print(f"\n/context 총 {total:,} = 설정(지연 제외) {resident:,} + Messages {cat('Messages'):,} "
          f"+ Compact {cat('Compact buffer'):,} = {resident + cat('Messages') + cat('Compact buffer'):,}"
          f" (차 {total - resident - cat('Messages') - cat('Compact buffer'):+,} — /context 표기가 100 단위 반올림)")

    flagged = sorted((n for n in nodes if "body_outlier" in n["flags"]),
                     key=lambda n: -n["body_tokens"])
    top = ", ".join(f"{n['name']}({n['body_tokens']:,})" for n in flagged[:5])
    print(f"body_outlier {len(flagged)}개 (상위: {top})")
    joined = sum(1 for n in nodes if n["verdict"])
    print(f"판정 붙은 노드 {joined} · 요약 {sum(1 for n in nodes if n['summary'])} "
          f"· 쓰임 {sum(1 for n in nodes if n['usage'])} · 설치시각 {sum(1 for n in nodes if n['installed_at'])}")
    print("--check ok" if not bad else f"--check FAILED ({bad})")
    return bad


def main() -> int:
    doc = build()
    out = DATA / "map.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(list(walk(doc["root"])))
    print(f"wrote {out} ({out.stat().st_size:,} bytes, 노드 {n}개)")
    if "--check" in sys.argv:
        return check(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
