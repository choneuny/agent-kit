#!/usr/bin/env python3
"""The card list for *this* machine — the part of the build that is not portable.

`decisions.py` holds the skeleton (card schema, token lookup, verdict lookup,
hook-output reading, file writing); this file names the actual handles: which
MCP servers, which hooks, which directories, which plugins.

It is an example, written against the maintainer's setup. Rewrite it for your
own — the procedure is in docs/guides/decision-cards.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from decisions import (
    ENABLED,
    GREP_LOG,
    HOME,
    HOWTO,
    JUDG,
    MEAS_MCP,
    ROOT,
    SUMM,
    brk,
    card,
    dir_card,
    est_text,
    injected_from_stdout,
    inv_of,
    item_tokens,
    mcp_card,
    read_text,
    rule_item,
    rule_pair,
    run_capture,
    transcript_match,
    usage_for,
    verdicts_for,
)

# ── hook output measurement ───────────────────────────────────────────────────
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


# ── cards ────────────────────────────────────────────────────────────────────
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
