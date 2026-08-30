#!/usr/bin/env bash
# agent-kit installer — idempotent. Re-running changes nothing that is already
# in place; `./install.sh --uninstall` takes it all back out.
#
# What it does:
#   Claude Code   ~/.claude/rules/<name>.md      symlink to rules/*.md
#                 ~/.claude/skills/<name>        symlink to skills/*
#                 ~/.claude/commands/refresh.md  symlink to skills/refresh/refresh.md
#                 ~/.claude/settings.json        adds one SessionStart hook entry
#   Codex         ~/.codex/skills/<name>         symlink to skills/*
#                 ~/.codex/AGENTS.md             a marked block carrying the rules
#                 ~/.codex/hooks.json            adds one SessionStart hook entry
#                                                (needs [features] hooks = true in config.toml)
#
# bash 3 compatible. Needs python3 (or node) only for the settings.json edit.

set -u

REPO=$(cd "$(dirname "$0")" && pwd)
HOOK_REL="skills/refresh/hooks/session-start.sh"
HOOK_PATH="$REPO/$HOOK_REL"
MARK_BEGIN="<!-- agent-kit:begin -->"
MARK_END="<!-- agent-kit:end -->"

CLAUDE_DIR="$HOME/.claude"
CODEX_DIR="$HOME/.codex"
SETTINGS="$CLAUDE_DIR/settings.json"
CODEX_AGENTS="$CODEX_DIR/AGENTS.md"
CODEX_HOOKS="$CODEX_DIR/hooks.json"
CODEX_CONFIG="$CODEX_DIR/config.toml"
CODEX_MATCHER="startup|resume|clear|compact"
HOOK_TIMEOUT=5

RULES="korean-writing docs-and-memory"
SKILLS="agent-concept-maps explain-with-pictures docs-upkeep refresh"

MODE=install
case "${1:-}" in
  --uninstall) MODE=uninstall ;;
  -h|--help)
    echo "usage: $0 [--uninstall]"
    exit 0 ;;
  "") ;;
  *)
    echo "unknown option: $1" >&2
    exit 2 ;;
esac

say() { printf '  %s\n' "$1"; }

# ── symlinks ─────────────────────────────────────────────────────────────
link() {  # link <target> <linkname>
  local target=$1 name=$2
  if [ -L "$name" ]; then
    if [ "$(readlink "$name")" = "$target" ]; then
      say "already linked   $name"
      return 0
    fi
    rm -f "$name"
  elif [ -e "$name" ]; then
    say "SKIPPED (exists, not a link)  $name"
    return 0
  fi
  mkdir -p "$(dirname "$name")"
  ln -s "$target" "$name" && say "linked           $name -> $target"
}

unlink_ours() {  # unlink_ours <target> <linkname>
  local target=$1 name=$2
  if [ -L "$name" ] && [ "$(readlink "$name")" = "$target" ]; then
    rm -f "$name" && say "removed link     $name"
  elif [ -e "$name" ]; then
    say "left alone       $name (not ours)"
  fi
}

# ── settings.json SessionStart hook ──────────────────────────────────────
json_edit() {  # json_edit <add|remove> <file> <claude|codex>
  local action=$1 target=$2 flavor=$3
  local script
  script=$(cat <<'PY'
import json, os, sys, time

action, settings_path, hook_path, hook_rel, flavor, matcher, timeout = sys.argv[1:8]

data = {}
text = ""
existed = os.path.exists(settings_path)
if existed:
    with open(settings_path, encoding="utf-8") as fh:
        text = fh.read().strip()
    if text:
        try:
            data = json.loads(text)
        except ValueError:
            print("PARSE_ERROR")
            sys.exit(3)

hooks = data.get("hooks") or {}
entries = hooks.get("SessionStart") or []

def ours(entry):
    for cmd in entry.get("hooks", []):
        if str(cmd.get("command", "")).endswith(hook_rel):
            return True
    return False

if action == "add":
    if any(ours(e) for e in entries):
        print("UNCHANGED")
        sys.exit(0)
    if flavor == "codex":
        entry = {
            "matcher": matcher,
            "hooks": [{"type": "command", "command": hook_path, "timeout": int(timeout)}],
        }
    else:
        entry = {"hooks": [{"type": "command", "command": hook_path}]}
    entries = entries + [entry]
    hooks["SessionStart"] = entries
    data["hooks"] = hooks
    status = "ADDED"
else:
    kept = [e for e in entries if not ours(e)]
    if len(kept) == len(entries):
        print("UNCHANGED")
        sys.exit(0)
    if kept:
        hooks["SessionStart"] = kept
    else:
        hooks.pop("SessionStart", None)
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    status = "REMOVED"

# only touch the file when something actually changes
if existed:
    backup = "%s.bak-%s" % (settings_path, time.strftime("%Y%m%dT%H%M%S"))
    with open(backup, "w", encoding="utf-8") as fh:
        fh.write(text if text else "{}")
    print("BACKUP\t%s" % backup)

parent = os.path.dirname(settings_path)
if parent:
    os.makedirs(parent, exist_ok=True)
tmp = settings_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
os.replace(tmp, settings_path)
print(status)
PY
)
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$script" | python3 - "$action" "$target" "$HOOK_PATH" "$HOOK_REL" "$flavor" "$CODEX_MATCHER" "$HOOK_TIMEOUT"
  elif command -v node >/dev/null 2>&1; then
    node -e "$(cat <<'JS'
const fs = require("fs"), path = require("path");
const [action, settingsPath, hookPath, hookRel, flavor, matcher, timeout] = process.argv.slice(1);
let data = {}, text = "";
const existed = fs.existsSync(settingsPath);
if (existed) {
  text = fs.readFileSync(settingsPath, "utf8").trim();
  if (text) { try { data = JSON.parse(text); } catch (e) { console.log("PARSE_ERROR"); process.exit(3); } }
}
const hooks = data.hooks || {};
const entries = hooks.SessionStart || [];
const ours = e => (e.hooks || []).some(c => String(c.command || "").endsWith(hookRel));
let status;
if (action === "add") {
  if (entries.some(ours)) { console.log("UNCHANGED"); process.exit(0); }
  const entry = flavor === "codex"
    ? { matcher: matcher, hooks: [{ type: "command", command: hookPath, timeout: Number(timeout) }] }
    : { hooks: [{ type: "command", command: hookPath }] };
  hooks.SessionStart = entries.concat([entry]);
  data.hooks = hooks;
  status = "ADDED";
} else {
  const kept = entries.filter(e => !ours(e));
  if (kept.length === entries.length) { console.log("UNCHANGED"); process.exit(0); }
  if (kept.length) hooks.SessionStart = kept; else delete hooks.SessionStart;
  if (Object.keys(hooks).length) data.hooks = hooks; else delete data.hooks;
  status = "REMOVED";
}
if (existed) {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
  const backup = settingsPath + ".bak-" + stamp;
  fs.writeFileSync(backup, text || "{}");
  console.log("BACKUP\t" + backup);
}
fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
fs.writeFileSync(settingsPath + ".tmp", JSON.stringify(data, null, 2) + "\n");
fs.renameSync(settingsPath + ".tmp", settingsPath);
console.log(status);
JS
)" "$action" "$target" "$HOOK_PATH" "$HOOK_REL" "$flavor" "$CODEX_MATCHER" "$HOOK_TIMEOUT"
  else
    echo "NO_RUNTIME"
  fi
}

apply_hook() {  # apply_hook <add|remove> <file> <claude|codex>
  local out status backup target=$2
  if [ "$1" = remove ] && [ ! -f "$target" ]; then
    say "nothing to undo  $target (no such file)"
    return 0
  fi
  out=$(json_edit "$1" "$2" "$3")
  status=$(printf '%s\n' "$out" | tail -1)
  backup=$(printf '%s\n' "$out" | sed -n 's/^BACKUP\t//p')
  [ -n "$backup" ] && say "backed up        $backup"
  case "$status" in
    ADDED)      say "hook added       $target  (SessionStart -> $HOOK_REL)" ;;
    REMOVED)    say "hook removed     $target" ;;
    UNCHANGED)  say "hook unchanged   $target" ;;
    PARSE_ERROR)say "SKIPPED          $target is not valid JSON — fix it and re-run" ;;
    NO_RUNTIME) say "SKIPPED          need python3 or node to edit $target" ;;
    *)          say "SKIPPED          could not edit $target ($status)" ;;
  esac
}

# Codex runs hooks only when config.toml turns the feature on. Editing a user's
# TOML by hand is risky, so this only looks and tells.
check_codex_feature() {
  if [ ! -f "$CODEX_CONFIG" ]; then
    say "NOTE             no $CODEX_CONFIG — add [features] with hooks = true to run the hook"
    return 0
  fi
  local enabled
  enabled=$(awk '
    /^[[:space:]]*\[/ { section = $0; gsub(/[][[:space:]]/, "", section) }
    section == "features" && /^[[:space:]]*hooks[[:space:]]*=[[:space:]]*true/ { print "yes"; exit }
  ' "$CODEX_CONFIG")
  if [ "$enabled" = yes ]; then
    say "feature on       $CODEX_CONFIG  ([features] hooks = true)"
  else
    say "NOTE             $CODEX_CONFIG has no [features] hooks = true — add it yourself or the hook never runs"
  fi
}

# ── Codex AGENTS.md block ────────────────────────────────────────────────
# Codex AGENTS.md has no @-import, so the rule bodies are copied in.
codex_block() {
  printf '%s\n' "$MARK_BEGIN"
  printf '%s\n' "<!-- agent-kit installs this block. Edit the repo, re-run install.sh. -->"
  printf '\n'
  local rule
  for rule in $RULES; do
    # drop the leading YAML frontmatter — it is harness metadata, not prose
    awk 'NR==1 && $0=="---" { fm=1; next } fm && $0=="---" { fm=0; next } !fm { print }' \
      "$REPO/rules/$rule.md"
    printf '\n'
  done
  printf '%s\n' "$MARK_END"
}

write_codex_block() {
  mkdir -p "$CODEX_DIR"
  local tmp="$CODEX_AGENTS.tmp"
  if [ -f "$CODEX_AGENTS" ] && grep -qF "$MARK_BEGIN" "$CODEX_AGENTS"; then
    awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
      $0 == b { skip = 1 }
      skip != 1 { print }
      $0 == e { skip = 0 }
    ' "$CODEX_AGENTS" > "$tmp"
  elif [ -f "$CODEX_AGENTS" ]; then
    cat "$CODEX_AGENTS" > "$tmp"
  else
    : > "$tmp"
  fi
  # drop trailing blank lines, then append a fresh block
  awk 'BEGIN{n=0} {lines[NR]=$0} END{last=NR; while (last>0 && lines[last]=="") last--; for(i=1;i<=last;i++) print lines[i]}' "$tmp" > "$tmp.trim"
  mv "$tmp.trim" "$tmp"
  [ -s "$tmp" ] && printf '\n' >> "$tmp"
  codex_block >> "$tmp"
  if [ -f "$CODEX_AGENTS" ] && cmp -s "$tmp" "$CODEX_AGENTS"; then
    rm -f "$tmp"
    say "block unchanged  $CODEX_AGENTS"
    return 0
  fi
  mv "$tmp" "$CODEX_AGENTS"
  say "rules block      $CODEX_AGENTS"
}

remove_codex_block() {
  [ -f "$CODEX_AGENTS" ] || return 0
  if ! grep -qF "$MARK_BEGIN" "$CODEX_AGENTS"; then
    say "no block         $CODEX_AGENTS"
    return 0
  fi
  local tmp="$CODEX_AGENTS.tmp"
  awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
    $0 == b { skip = 1 }
    skip != 1 { print }
    $0 == e { skip = 0 }
  ' "$CODEX_AGENTS" > "$tmp"
  mv "$tmp" "$CODEX_AGENTS"
  say "block removed    $CODEX_AGENTS"
}

# ── run ──────────────────────────────────────────────────────────────────
echo "agent-kit  $REPO"

if [ "$MODE" = install ]; then
  echo "Claude Code"
  for r in $RULES; do link "$REPO/rules/$r.md" "$CLAUDE_DIR/rules/$r.md"; done
  for s in $SKILLS; do link "$REPO/skills/$s" "$CLAUDE_DIR/skills/$s"; done
  link "$REPO/skills/refresh/refresh.md" "$CLAUDE_DIR/commands/refresh.md"
  apply_hook add "$SETTINGS" claude

  echo "Codex"
  for s in $SKILLS; do link "$REPO/skills/$s" "$CODEX_DIR/skills/$s"; done
  write_codex_block
  apply_hook add "$CODEX_HOOKS" codex
  check_codex_feature

  echo
  echo "Done. Start a new session to pick it up."
  echo "context-diet (tools/context-diet) installs on its own — see its SKILL.md."
else
  echo "Claude Code"
  for r in $RULES; do unlink_ours "$REPO/rules/$r.md" "$CLAUDE_DIR/rules/$r.md"; done
  for s in $SKILLS; do unlink_ours "$REPO/skills/$s" "$CLAUDE_DIR/skills/$s"; done
  unlink_ours "$REPO/skills/refresh/refresh.md" "$CLAUDE_DIR/commands/refresh.md"
  apply_hook remove "$SETTINGS" claude

  echo "Codex"
  for s in $SKILLS; do unlink_ours "$REPO/skills/$s" "$CODEX_DIR/skills/$s"; done
  remove_codex_block
  apply_hook remove "$CODEX_HOOKS" codex

  echo
  echo "Uninstalled. settings.json backups are left in place."
fi
exit 0
