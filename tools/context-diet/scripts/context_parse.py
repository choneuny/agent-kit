#!/usr/bin/env python3
"""Parse a `/context` dump into measured JSON, join it with the file inventory,
and fit the token-estimate coefficients from the rows that are measured exactly.

Reads only (except data/*.json it writes).

  uv run scripts/context_parse.py data/context-samples/2026-08-22-fable-cli.md
  uv run scripts/context_parse.py --from-transcript <session.jsonl>
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory as inv  # noqa: E402  (sibling script, reused helpers)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SAMPLES = DATA / "context-samples"


# --- parsing ------------------------------------------------------------------

TOK_RE = re.compile(r"^(?P<lt><)?\s*(?P<approx>~)?\s*(?P<num>[\d.]+)\s*(?P<k>k)?$", re.I)


def parse_tokens(s: str) -> dict:
    """'5.8k'->5800, '~80'->80 approx, '< 20'->20 approx+upper_bound, '392'->392."""
    m = TOK_RE.match(s.strip())
    if not m:
        raise ValueError(f"unparseable token cell: {s!r}")
    n = float(m["num"]) * (1000 if m["k"] else 1)
    out = {"tokens": round(n)}
    if m["approx"] or m["lt"]:
        out["approx"] = True
    if m["lt"]:
        out["upper_bound"] = True
    return out


def rows(md: str, heading: str) -> list[list[str]]:
    """Pipe-table body rows under a `### heading` (or the whole doc for '')."""
    if heading:
        i = md.find(f"### {heading}")
        if i < 0:
            return []
        j = md.find("\n### ", i + 1)
        block = md[i: j if j > 0 else len(md)]
    else:
        block = md
    out = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        out.append(cells)
    return out[1:]  # drop header row


def parse_context(md: str, source: str) -> dict:
    model = re.search(r"\*\*Model:\*\*\s*(\S+)", md)
    total = re.search(r"\*\*Tokens:\*\*\s*([\d.]+k?)\s*/", md)
    out = {
        "source_file": source,
        "model": model.group(1) if model else None,
        "total_tokens": parse_tokens(total.group(1))["tokens"] if total else None,
        "categories": {},
        "mcp": {"tools": [], "by_server": {}},
        "agents": [],
        "memory_files": [],
        "skills": [],
    }
    for name, tok, pct in rows(md, "Estimated usage by category"):
        out["categories"][name] = {**parse_tokens(tok), "pct": float(pct.rstrip("%"))}

    for name, server, tok in rows(md, "MCP Tools"):
        t = parse_tokens(tok)
        out["mcp"]["tools"].append({"name": name, "server": server, **t})
        agg = out["mcp"]["by_server"].setdefault(server, {"count": 0, "tokens": 0})
        agg["count"] += 1
        agg["tokens"] += t["tokens"]

    for name, src, tok in rows(md, "Custom Agents"):
        out["agents"].append({"name": name, "source": src, **parse_tokens(tok)})
    for typ, path, tok in rows(md, "Memory Files"):
        out["memory_files"].append({"type": typ, "path": path, **parse_tokens(tok)})
    for name, src, tok in rows(md, "Skills"):
        out["skills"].append({"name": name, "source": src, **parse_tokens(tok)})
    return out


# --- transcript ---------------------------------------------------------------

def from_transcript(jsonl: Path) -> Path:
    """Pull the last /context output out of a session transcript into a sample file."""
    found = None
    with jsonl.open(encoding="utf-8") as f:
        for line in f:
            if "Estimated usage by category" not in line:
                continue
            rec = json.loads(line)
            content = rec.get("content") or ""
            if not isinstance(content, str) or "local-command-stdout" not in content:
                continue
            body = re.sub(r"</?local-command-stdout>", "", content).strip()
            found = (body, rec.get("timestamp", ""))
    if not found:
        raise SystemExit(f"no /context output found in {jsonl}")
    body, ts = found
    model = (re.search(r"\*\*Model:\*\*\s*(\S+)", body) or [None, "unknown"])[1]
    if ts:
        date = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()
    else:
        date = datetime.now().astimezone().date().isoformat()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    out = SAMPLES / f"{date}-{model}.md"
    out.write_text(body + "\n", encoding="utf-8")
    print(f"extracted {len(body)} chars -> {out}")
    return out


# --- join with inventory ------------------------------------------------------

def index_inventory(items: list[dict]) -> tuple[dict, dict]:
    """(by realpath, by name) — enabled items win when a name is duplicated."""
    by_path, by_name = {}, {}
    for it in items:
        try:
            rp = str(Path(it["path"]).resolve())
        except OSError:
            rp = it["path"]
        by_path.setdefault(rp, it)
        prev = by_name.get(it["name"])
        if prev is None or (it["enabled"] and not prev["enabled"]):
            by_name[it["name"]] = it
    return by_path, by_name


def join(measured: dict, items: list[dict]) -> dict:
    by_path, by_name = index_inventory(items)
    report = {}

    def pair(kind, meas, key_fn, inv_kinds):
        hit, miss = [], []
        for m in meas:
            it = key_fn(m)
            if it and it["kind"] in inv_kinds:
                hit.append((m, it))
            else:
                miss.append(m)
        pool = {i["name"] for i in items if i["kind"] in inv_kinds and i["enabled"]}
        matched_names = {i["name"] for _, i in hit}
        report[kind] = {
            "measured": len(meas), "matched": len(hit),
            "unmatched_measured": [m.get("name") or m.get("path") for m in miss],
            "unmatched_inventory": sorted(pool - matched_names),
        }
        return hit

    mem = pair("memory_files", measured["memory_files"],
               lambda m: by_path.get(str(Path(m["path"]).resolve())
                                     if Path(m["path"]).exists() else m["path"]),
               {"rule", "memory"})
    agents = pair("agents", measured["agents"], lambda m: by_name.get(m["name"]), {"agent"})
    pair("skills", measured["skills"], lambda m: by_name.get(m["name"]), {"skill", "command"})
    return {"report": report, "memory": mem, "agents": agents}


# --- calibration --------------------------------------------------------------

def sample_of(m: dict, it: dict) -> dict | None:
    """Char counts for the text the harness actually loaded for this item."""
    text = inv.read_text(Path(it["path"]))
    if it["kind"] == "agent":  # only the listing (name + description) is in context
        text = inv.listing_text(inv.frontmatter(text))
    if not text:
        return None
    a, n = inv.split_chars(text)
    return {"path": it["path"], "kind": it["kind"], "name": it["name"],
            "ascii": a, "non_ascii": n, "tokens": m["tokens"]}


def residuals(samples: list[dict], coef: dict) -> list[dict]:
    out = []
    for s in samples:
        est = round(s["ascii"] / coef["ascii_div"] + s["non_ascii"] * coef["non_ascii_per_char"])
        out.append({**s, "est": est, "resid": est - s["tokens"],
                    "rel": (est - s["tokens"]) / max(s["tokens"], 1)})
    return out


# --- main ---------------------------------------------------------------------

def main() -> int:
    argv = sys.argv[1:]
    check = "--check" in argv
    argv = [a for a in argv if a != "--check"]
    if argv[:1] == ["--from-transcript"]:
        sample = from_transcript(Path(argv[1]).expanduser())
    else:
        sample = Path(argv[0]) if argv else SAMPLES / "2026-08-22-fable-cli.md"

    md = sample.read_text(encoding="utf-8")
    measured = parse_context(md, str(sample))
    (DATA / "context-measured.json").write_text(
        json.dumps(measured, ensure_ascii=False, indent=2), encoding="utf-8")

    cat = measured["categories"]
    print(f"{sample}  model={measured['model']}  total={measured['total_tokens']:,}")
    print(f"  categories={len(cat)}  mcp tools={len(measured['mcp']['tools'])} "
          f"servers={len(measured['mcp']['by_server'])}  agents={len(measured['agents'])} "
          f"memory={len(measured['memory_files'])}  skills={len(measured['skills'])}")

    items = inv.load_json(DATA / "inventory.json").get("items", [])
    if not items:
        print("no data/inventory.json — run scripts/inventory.py first", file=sys.stderr)
        return 1
    j = join(measured, items)
    print("\n조인 매칭률:")
    for kind, r in j["report"].items():
        print(f"  {kind:<13} {r['matched']}/{r['measured']}")
        if r["unmatched_measured"]:
            print(f"    실측에만 있음 ({len(r['unmatched_measured'])}): "
                  f"{', '.join(map(str, r['unmatched_measured']))}")
        if r["unmatched_inventory"]:
            print(f"    재고에만 있음 ({len(r['unmatched_inventory'])}): "
                  f"{', '.join(r['unmatched_inventory'])}")

    samples = [s for s in (sample_of(m, it) for m, it in j["memory"] + j["agents"]) if s]
    coef = inv.fit(samples)
    if not coef:
        print("calibration fit degenerate", file=sys.stderr)
        return 1
    cal = {**coef, "source": f"context-measured:{sample.name}",
           "measured_at": datetime.now(timezone.utc).isoformat(), "samples": samples}
    (DATA / "calibration.json").write_text(json.dumps(cal, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(f"\n보정 계수: ascii_div={coef['ascii_div']:.3f} "
          f"non_ascii_per_char={coef['non_ascii_per_char']:.3f}  (표본 {len(samples)}개)")

    res = residuals(samples, coef)
    worst = sorted(res, key=lambda r: -abs(r["rel"]))[:5]
    print("  최악 잔차 5개 (est - 실측):")
    for r in worst:
        print(f"    {r['kind']:<6} {r['name'][:44]:<44} 실측 {r['tokens']:>6,} "
              f"est {r['est']:>6,} ({r['rel']:+.1%})")
    tot_m = sum(r["tokens"] for r in res)
    tot_e = sum(r["est"] for r in res)
    print(f"  표본 합계: 실측 {tot_m:,} est {tot_e:,} ({(tot_e-tot_m)/tot_m:+.1%})")

    # skills are '~' approximations — excluded from the fit, compared only
    sk_pairs = []
    _, by_name = index_inventory(items)
    for m in measured["skills"]:
        it = by_name.get(m["name"])
        if it and it["kind"] in ("skill", "command"):
            s = {"tokens": m["tokens"],
                 "ascii": 0, "non_ascii": 0, "name": m["name"], "kind": it["kind"],
                 "path": it["path"]}
            text = inv.listing_text(inv.frontmatter(inv.read_text(Path(it["path"]))))
            s["ascii"], s["non_ascii"] = inv.split_chars(text)
            sk_pairs.append(s)
    if sk_pairs:
        r = residuals(sk_pairs, coef)
        tm, te = sum(x["tokens"] for x in r), sum(x["est"] for x in r)
        print(f"  (검증) 스킬·명령 {len(r)}개 합계: 실측 {tm:,} est {te:,} "
              f"({(te-tm)/tm:+.1%}) — 실측이 '~' 근사라 보정 표본에서 제외")

    if check:
        # 표본 불변식만 — 특정 표본의 개수·값에 묶지 않는다 (08-22 표본 하드코딩이 새 표본에서 깨졌다)
        assert measured["mcp"]["tools"], "no MCP tools parsed"
        for srv, info in measured["mcp"]["by_server"].items():
            s = sum(t["tokens"] for t in measured["mcp"]["tools"] if t["server"] == srv)
            assert info["tokens"] == s, f"{srv} sum mismatch: {info['tokens']} != {s}"
        mem_sum = sum(m["tokens"] for m in measured["memory_files"])
        cat_mem = measured["categories"]["Memory files"]["tokens"]
        # 범주 값과 행 합은 표기 반올림(행당 ±50)만큼 어긋난다
        tol = max(200, 50 * len(measured["memory_files"]))
        assert abs(mem_sum - cat_mem) <= tol, (mem_sum, cat_mem, tol)
        assert parse_tokens("5.8k")["tokens"] == 5800
        assert parse_tokens("< 20") == {"tokens": 20, "approx": True, "upper_bound": True}
        assert parse_tokens("~80") == {"tokens": 80, "approx": True}
        assert parse_tokens("392") == {"tokens": 392}
        print("\n--check ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
