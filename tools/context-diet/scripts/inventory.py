#!/usr/bin/env python3
"""Inventory everything the Claude Code harness loads into a session, with token estimates.

Reads only. Writes data/inventory.json (and data/calibration.json when an API key is present).
"""
from __future__ import annotations

import json
import os
import platform
import re
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"
AGENTS = HOME / ".agents"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Token estimate coefficients. ASCII is ~4 bytes/token; Korean syllables cost far more
# (roughly 1.5 tokens per char on Claude's tokenizer). Overridden by data/calibration.json.
ASCII_DIV = 4.0
NON_ASCII_PER_CHAR = 1.5

COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
COUNT_TOKENS_MODEL = "claude-sonnet-4-5"


# --- token estimation ---------------------------------------------------------

def split_chars(text: str) -> tuple[int, int]:
    """Return (ascii_char_count, non_ascii_char_count)."""
    a = sum(1 for c in text if ord(c) < 128)
    return a, len(text) - a


def estimate(text: str, coef: dict) -> int:
    a, n = split_chars(text)
    return round(a / coef["ascii_div"] + n * coef["non_ascii_per_char"])


def mtime_of(path) -> str | None:
    """ISO mtime of the canonical file (symlinks resolved). None if it is not a real path."""
    if not path:
        return None
    try:
        p = Path(path).resolve()
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return None


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# --- calibration --------------------------------------------------------------

def count_tokens_api(text: str, key: str) -> int | None:
    body = json.dumps({
        "model": COUNT_TOKENS_MODEL,
        "messages": [{"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(
        COUNT_TOKENS_URL, data=body, method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["input_tokens"]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        print(f"warning: count_tokens failed: {e}", file=sys.stderr)
        return None


def fit(samples: list[dict]) -> dict | None:
    """Least squares for tokens = a*ascii + b*nonascii (no intercept). 2x2 normal equations."""
    saa = sum(s["ascii"] ** 2 for s in samples)
    snn = sum(s["non_ascii"] ** 2 for s in samples)
    san = sum(s["ascii"] * s["non_ascii"] for s in samples)
    sat = sum(s["ascii"] * s["tokens"] for s in samples)
    snt = sum(s["non_ascii"] * s["tokens"] for s in samples)
    det = saa * snn - san * san
    if abs(det) < 1e-9:
        return None
    a = (sat * snn - snt * san) / det
    b = (snt * saa - sat * san) / det
    if a <= 0 or b <= 0:
        return None
    return {"ascii_div": 1.0 / a, "non_ascii_per_char": b}


def calibrate(candidates: list[Path], key: str) -> dict | None:
    """Pick 5 ASCII-heavy and 5 Korean-heavy files, measure them, fit the two coefficients."""
    scored = []
    for p in candidates:
        t = read_text(p)
        if not (200 < len(t) < 20000):
            continue
        a, n = split_chars(t)
        scored.append((n / max(a + n, 1), p, t, a, n))
    if len(scored) < 4:
        print("warning: not enough calibration candidates", file=sys.stderr)
        return None
    scored.sort(key=lambda x: x[0])
    picked = scored[:5] + scored[-5:]

    samples = []
    for ratio, p, t, a, n in picked:
        tok = count_tokens_api(t, key)
        if tok is None:
            continue
        samples.append({"path": str(p), "ascii": a, "non_ascii": n, "tokens": tok,
                        "non_ascii_ratio": round(ratio, 3)})
    if len(samples) < 4:
        print("warning: too few successful count_tokens samples; keeping defaults", file=sys.stderr)
        return None
    coef = fit(samples)
    if coef is None:
        print("warning: calibration fit degenerate; keeping defaults", file=sys.stderr)
        return None
    return {**coef, "source": "count_tokens_api", "model": COUNT_TOKENS_MODEL,
            "measured_at": datetime.now(timezone.utc).isoformat(), "samples": samples}


# --- frontmatter --------------------------------------------------------------

def frontmatter(text: str) -> dict:
    """Parse the leading --- YAML block. Single-line scalars only; folds `key: >-` blocks."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out, key, buf = {}, None, []
    for line in text[3:end].splitlines():
        if line[:1] not in (" ", "\t", "") and ":" in line:
            if key:
                out[key] = " ".join(buf).strip()
            k, _, v = line.partition(":")
            key, buf = k.strip(), []
            v = v.strip()
            if v and v not in ("|", ">", ">-", "|-"):
                out[key] = v.strip('"').strip("'")
                key = None
        elif key is not None:
            buf.append(line.strip())
    if key:
        out[key] = " ".join(buf).strip()
    return out


# --- item construction --------------------------------------------------------

def make_item(kind, name, path, enabled, source, text, coef, *, listing=None, **extra):
    item = {
        "kind": kind, "name": name, "path": str(path), "enabled": enabled,
        "source": source, "bytes": len(text.encode("utf-8")),
    }
    if listing is not None:
        item["listing_bytes"] = len(listing.encode("utf-8"))
        item["tokens_est"] = estimate(listing, coef)
        item["tokens_body_est"] = estimate(text, coef)
    else:
        item["tokens_est"] = estimate(text, coef)
    if "description" not in extra:
        fm = frontmatter(text) if text.startswith("---") else {}
        desc = fm.get("description") or first_heading(text)
        item["description"] = desc or None
    item.update(extra)
    return item


def first_heading(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def listing_text(fm: dict) -> str:
    return f"{fm.get('name', '')}\n{fm.get('description', '')}"


# --- collectors ---------------------------------------------------------------

def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def collect_rules(coef) -> list[dict]:
    """Rules may live in ~/.claude/rules or in a separate repo it symlinks into.
    Both roots are walked and realpath dedupes them. Only common/ is loaded into
    every session (observed in the live system prompt)."""
    items, seen = [], set()
    for base in (CLAUDE / "rules", AGENTS / "rules"):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            real = p.resolve()
            if real in seen:
                continue
            seen.add(real)
            enabled = real.parent.name == "common"
            items.append(make_item(
                "rule", real.stem, real, enabled, "dir-scan", read_text(real), coef,
                note=None if enabled else "language-specific dir; not in the session system prompt",
            ))
    if (CLAUDE / "CLAUDE.md").exists():
        t = read_text(CLAUDE / "CLAUDE.md")
        items.append(make_item("rule", "CLAUDE.md(global)", CLAUDE / "CLAUDE.md",
                               True, "dir-scan", t, coef))
    return items


def enabled_plugins(settings: dict) -> dict[str, bool]:
    return settings.get("enabledPlugins", {})


def plugin_roots(settings: dict) -> list[dict]:
    """Installed plugin roots from installed_plugins.json, tagged with enabled state.
    Layout: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/"""
    installed = load_json(CLAUDE / "plugins" / "installed_plugins.json").get("plugins", {})
    en = enabled_plugins(settings)
    out = []
    for key, entries in installed.items():
        for e in entries:
            root = Path(e.get("installPath", ""))
            if not root.is_dir():
                continue
            out.append({"key": key, "name": key.split("@")[0], "root": root,
                        "enabled": bool(en.get(key, False))})
    return out


def collect_skills(coef, plugins) -> list[dict]:
    items = []
    for d in sorted((CLAUDE / "skills").glob("*")):
        if not d.is_dir():
            continue
        sk = d / "SKILL.md"
        if not sk.exists():
            items.append(make_item("skill", d.name, d, False, "dir-scan", "", coef,
                                   listing="", note="no SKILL.md — not loaded as a skill"))
            continue
        t = read_text(sk)
        items.append(make_item("skill", frontmatter(t).get("name", d.name), sk.resolve(),
                               True, "dir-scan", t, coef, listing=listing_text(frontmatter(t))))
    for pl in plugins:
        for sk in sorted(pl["root"].glob("skills/*/SKILL.md")):
            t = read_text(sk)
            fm = frontmatter(t)
            items.append(make_item("skill", f"{pl['name']}:{fm.get('name', sk.parent.name)}",
                                   sk, pl["enabled"],
                                   str(CLAUDE / "settings.json") + "#enabledPlugins",
                                   t, coef, listing=listing_text(fm), plugin=pl["key"]))
    return items


def collect_md_dir(kind, directory, coef, source, enabled=True, prefix="") -> list[dict]:
    items = []
    for p in sorted(directory.glob("*.md")) if directory.is_dir() else []:
        t = read_text(p)
        fm = frontmatter(t)
        items.append(make_item(kind, prefix + fm.get("name", p.stem), p, enabled, source,
                               t, coef, listing=listing_text(fm)))
    return items


def collect_disabled_dir(kind, directory, coef) -> list[dict]:
    """Items turned off by moving them to ~/.claude/<kind>s-disabled/ (2026-08-24 convention —
    an inner hidden dir like commands/.disabled/ doesn't stop discovery, so off-switches live
    outside the loaded tree instead)."""
    items = []
    for p in sorted(directory.glob("*.md")) if directory.is_dir() else []:
        t = read_text(p)
        fm = frontmatter(t)
        items.append(make_item(kind, fm.get("name", p.stem), p, False, "disabled-dir", t, coef,
                               listing=listing_text(fm),
                               note=f"~/.claude/{directory.name}/로 옮겨져 꺼짐 — 되돌리기는 data/actions.jsonl"))
    return items


def collect_commands(coef, plugins) -> list[dict]:
    items = collect_md_dir("command", CLAUDE / "commands", coef, "dir-scan")
    for pl in plugins:
        items += collect_md_dir("command", pl["root"] / "commands", coef,
                                str(CLAUDE / "settings.json") + "#enabledPlugins",
                                pl["enabled"], prefix=f"{pl['name']}:")
    items += collect_disabled_dir("command", CLAUDE / "commands-disabled", coef)
    return items


def collect_agents(coef, plugins) -> list[dict]:
    items = collect_md_dir("agent", CLAUDE / "agents", coef, "dir-scan")
    for pl in plugins:
        items += collect_md_dir("agent", pl["root"] / "agents", coef,
                                str(CLAUDE / "settings.json") + "#enabledPlugins",
                                pl["enabled"], prefix=f"{pl['name']}:")
    items += collect_disabled_dir("agent", CLAUDE / "agents-disabled", coef)
    return items


def settings_hook_commands(settings: dict) -> list[tuple[str, str]]:
    """(event, command) for every registered hook command in settings.json."""
    out = []
    for event, groups in (settings.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks", []) or []:
                if h.get("command"):
                    out.append((event, h["command"]))
    return out


def collect_hooks(coef, settings, plugins) -> list[dict]:
    items = []
    src = str(CLAUDE / "settings.json")
    registered_scripts = set()
    for event, cmd in settings_hook_commands(settings):
        # last path-looking token is the script
        script = next((tok for tok in reversed(cmd.split())
                       if "/" in tok and not tok.startswith("-")), "")
        p = Path(os.path.expanduser(script.strip('"')))
        text = read_text(p) if p.is_file() else ""
        if p.is_file():
            registered_scripts.add(p.resolve())
        items.append(make_item("hook", f"{event}:{p.name or cmd[:40]}", p, True, src, text, coef,
                               event=event, command=cmd,
                               note="script body; the context cost is the hook's output, not this file"))
    for pl in plugins:
        hooks_cfg = load_json(pl["root"] / ".claude-plugin" / "plugin.json").get("hooks")
        cfg_path = pl["root"] / str(hooks_cfg).lstrip("./") if hooks_cfg else None
        if not (cfg_path and cfg_path.is_file()):
            continue
        for event, cmd in settings_hook_commands(load_json(cfg_path)):
            items.append(make_item("hook", f"{pl['name']}:{event}", cfg_path, pl["enabled"],
                                   str(cfg_path), "", coef, event=event, command=cmd,
                                   plugin=pl["key"],
                                   note="plugin hook; body not loaded into context"))
    for d in (CLAUDE / "hooks", CLAUDE / "scripts" / "hooks"):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.resolve() in registered_scripts:
                continue
            items.append(make_item("hook", p.name, p, False, "dir-scan", "", coef,
                                   note="present on disk but not registered in settings.json"))
    return items


def collect_mcp(coef, settings, plugins) -> list[dict]:
    note = "실측만 가능 — 도구 스키마는 파일에 없다"
    items = []
    cj = CLAUDE.parent / ".claude.json"
    conf = load_json(cj)
    for name in (conf.get("mcpServers") or {}):
        items.append({"kind": "mcp", "name": name, "path": str(cj), "enabled": True,
                      "source": str(cj) + "#mcpServers", "bytes": 0,
                      "tokens_est": None, "note": note})
    for proj, pv in (conf.get("projects") or {}).items():
        for name in (pv.get("mcpServers") or {}):
            items.append({"kind": "mcp", "name": name, "path": str(cj), "enabled": True,
                          "source": f"{cj}#projects[{proj}].mcpServers", "bytes": 0,
                          "tokens_est": None, "project": proj, "note": note})
    for name in (settings.get("mcpServers") or {}):
        items.append({"kind": "mcp", "name": name, "path": str(CLAUDE / "settings.json"),
                      "enabled": True, "source": str(CLAUDE / "settings.json") + "#mcpServers",
                      "bytes": 0, "tokens_est": None, "note": note})
    for pl in plugins:
        for fn in (".mcp.json", "mcp-servers.json"):
            f = pl["root"] / fn
            if not f.is_file():
                continue
            for name in (load_json(f).get("mcpServers") or {}):
                items.append({"kind": "mcp", "name": f"{pl['name']}:{name}", "path": str(f),
                              "enabled": pl["enabled"], "source": str(f), "bytes": 0,
                              "tokens_est": None, "plugin": pl["key"], "note": note})
    return items


def collect_memory(coef) -> list[dict]:
    """Claude Code loads only the memory of the project matching cwd, so only that one
    is enabled. Project dir name = the path with every non-alphanumeric char replaced by '-'."""
    # cwd may sit inside a subdir of the registered project, so walk up to the nearest match.
    cwd = Path.cwd()
    cwd_key = ""
    for d in [cwd, *cwd.parents]:
        k = re.sub(r"[^A-Za-z0-9]", "-", str(d))
        if (CLAUDE / "projects" / k / "memory" / "MEMORY.md").is_file():
            cwd_key = k
            break
    items = []
    # Project instruction files (CLAUDE.md / AGENTS.md) load for cwd and every parent dir.
    for d in [*reversed(cwd.parents), cwd]:
        for fn in ("CLAUDE.md", "AGENTS.md"):
            p = d / fn
            if p.is_file():
                items.append(make_item("memory", str(p), p, True, "cwd-walk",
                                       read_text(p), coef, note="project instruction file"))
    for p in sorted((CLAUDE / "projects").glob("*/memory/MEMORY.md")):
        proj = p.parent.parent.name
        items.append(make_item("memory", proj, p, proj == cwd_key, "dir-scan",
                               read_text(p), coef, project=proj,
                               note="only the cwd project's memory loads per session"))
    return items


# --- output -------------------------------------------------------------------

GROUPS = [
    ("MCP 도구", ["mcp"]),
    ("메모리·규칙", ["rule", "memory"]),
    ("스킬 목록", ["skill", "command"]),   # /context "Skills" (commands list as skills)
    ("커스텀 에이전트", ["agent"]),          # /context "Custom Agents"
]


def render(items: list[dict], totals: dict) -> str:
    rows = [("kind", "count", "tok(enabled)", "tok(all)")]
    for kind in sorted(totals):
        t = totals[kind]
        rows.append((kind, str(t["count"]),
                     "n/a" if t["tokens_est"] is None else f"{t['tokens_est']:,}",
                     "n/a" if t["tokens_est_all"] is None else f"{t['tokens_est_all']:,}"))
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    out = []
    for i, r in enumerate(rows):
        out.append("  ".join(r[j].ljust(w[j]) if j == 0 else r[j].rjust(w[j]) for j in range(4)))
        if i == 0:
            out.append("  ".join("-" * w[j] for j in range(4)))
    out.append("")
    out.append("/context 실측 대응 묶음 (enabled only):")
    for label, kinds in GROUPS:
        vals = [totals[k]["tokens_est"] for k in kinds if k in totals]
        s = "n/a (실측만 가능)" if all(v is None for v in vals) else f"{sum(v or 0 for v in vals):,}"
        out.append(f"  {label:<14} {s:>20}")
    return "\n".join(out)


def main() -> int:
    check = "--check" in sys.argv
    DATA.mkdir(exist_ok=True)

    coef = {"ascii_div": ASCII_DIV, "non_ascii_per_char": NON_ASCII_PER_CHAR,
            "source": "default"}
    cal_file = DATA / "calibration.json"
    if cal_file.is_file():
        saved = load_json(cal_file)
        if saved.get("ascii_div") and saved.get("non_ascii_per_char"):
            coef = saved

    settings = load_json(CLAUDE / "settings.json")
    plugins = plugin_roots(settings)

    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        cand = sorted((AGENTS / "rules" / "common").glob("*.md")) + \
               sorted((CLAUDE / "agents").glob("*.md"))
        new = calibrate(cand, key)
        if new:
            cal_file.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
            coef = new
    else:
        print("warning: ANTHROPIC_API_KEY unset — using default coefficients "
              f"(ascii/{ASCII_DIV}, non-ascii*{NON_ASCII_PER_CHAR})", file=sys.stderr)

    items = (collect_rules(coef) + collect_skills(coef, plugins)
             + collect_commands(coef, plugins) + collect_agents(coef, plugins)
             + collect_hooks(coef, settings, plugins) + collect_mcp(coef, settings, plugins)
             + collect_memory(coef))

    for it in items:
        it["mtime"] = mtime_of(it.get("path"))

    totals: dict[str, dict] = {}
    for it in items:
        t = totals.setdefault(it["kind"], {"count": 0, "tokens_est": 0, "tokens_est_all": 0,
                                           "_measurable": False})
        t["count"] += 1
        if it["tokens_est"] is not None:
            t["_measurable"] = True
            t["tokens_est_all"] += it["tokens_est"]
            if it["enabled"]:
                t["tokens_est"] += it["tokens_est"]
    for t in totals.values():
        if not t.pop("_measurable"):
            t["tokens_est"] = t["tokens_est_all"] = None

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": f"{socket.gethostname()} ({platform.system()})",
        "calibration": coef,
        "totals": totals,
        "items": items,
    }
    (DATA / "inventory.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(render(items, totals))

    if check:
        n_settings_hooks = len(settings_hook_commands(settings))
        got = sum(1 for i in items
                  if i["kind"] == "hook" and i["source"] == str(CLAUDE / "settings.json"))
        assert got == n_settings_hooks, f"settings hooks {got} != {n_settings_hooks}"
        n_plugins_on = sum(1 for p in plugins if p["enabled"])
        assert n_plugins_on == sum(1 for v in enabled_plugins(settings).values() if v), \
            "enabled plugin count mismatch"
        assert all(i["tokens_est"] is None for i in items if i["kind"] == "mcp"), \
            "mcp items must not carry a file-based token estimate"
        for kind, dirname in (("agent", "agents-disabled"), ("command", "commands-disabled")):
            d = CLAUDE / dirname
            n_files = len(list(d.glob("*.md"))) if d.is_dir() else 0
            n_items = sum(1 for i in items if i["kind"] == kind and not i["enabled"]
                          and i["source"] == "disabled-dir")
            assert n_files == n_items, \
                f"{dirname}: {n_files} files != {n_items} disabled-dir items"
        print("\n--check ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
