#!/usr/bin/env bash
# agent-kit / refresh — SessionStart hook.
#
# Injects a refresh snapshot written by the `refresh` skill into a fresh
# session, then retires it so it is never injected twice.
#
# Conditions (all must hold):
#   1. ~/.agent-kit/refresh-snapshot.md exists
#   2. it is 64 KiB or smaller
#   3. its `created:` timestamp is under an hour old
#   4. its `cwd:` matches the directory this session started in
#
# On success the snapshot body goes to stdout — Claude Code puts a SessionStart
# hook's stdout into the session context. Every path exits 0; a broken snapshot
# must never break a session.
#
# bash 3 compatible. No jq.

set -u

KIT_DIR="${AGENT_KIT_STATE_DIR:-$HOME/.agent-kit}"
SNAPSHOT="$KIT_DIR/refresh-snapshot.md"
CONSUMED="$KIT_DIR/refresh-snapshot.consumed"
LOG="$KIT_DIR/refresh.log"
MAX_BYTES=65536
MAX_AGE_SECONDS=3600

log() {
  [ -d "$KIT_DIR" ] || return 0
  printf '%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG" 2>/dev/null || true
}

retire() {
  mv "$SNAPSHOT" "$CONSUMED" 2>/dev/null || true
}

[ -f "$SNAPSHOT" ] || exit 0

# ── the directory this session started in ────────────────────────────────
# Claude Code feeds the hook a JSON object on stdin that carries "cwd".
# Read it without blocking, and fall back to the process working directory.
HOOK_INPUT=""
IFS= read -r -t 2 -d '' HOOK_INPUT 2>/dev/null || true
SESSION_CWD=$(printf '%s' "$HOOK_INPUT" \
  | tr ',' '\n' \
  | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
  | head -1)
[ -n "$SESSION_CWD" ] || SESSION_CWD="$PWD"

# ── field readers ────────────────────────────────────────────────────────
field() {
  sed -n "s/^$1:[[:space:]]*//p" "$SNAPSHOT" 2>/dev/null \
    | head -1 | tr -d '"' | sed 's/[[:space:]]*$//'
}

# ── 2. size ──────────────────────────────────────────────────────────────
SIZE=$(wc -c < "$SNAPSHOT" 2>/dev/null | tr -d '[:space:]')
[ -n "$SIZE" ] || SIZE=0
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  log "skipped oversize ${SIZE}B"
  retire
  exit 0
fi

# ── 3. freshness ─────────────────────────────────────────────────────────
# Prefer the declared `created:` stamp. Fall back to file mtime when neither
# GNU date nor python3 can parse it, so a hand-written snapshot still works.
CREATED=$(field created)
FRESH=""
if [ -n "$CREATED" ]; then
  NOW=$(date +%s 2>/dev/null)
  CREATED_EPOCH=$(date -d "$CREATED" +%s 2>/dev/null)
  if [ -z "$CREATED_EPOCH" ] && command -v python3 >/dev/null 2>&1; then
    CREATED_EPOCH=$(python3 -c '
import sys
from datetime import datetime, timezone
raw = sys.argv[1].strip().replace("Z", "+00:00")
try:
    ts = datetime.fromisoformat(raw)
except ValueError:
    sys.exit(1)
if ts.tzinfo is None:
    ts = ts.replace(tzinfo=timezone.utc)
print(int(ts.timestamp()))
' "$CREATED" 2>/dev/null)
  fi
  if [ -n "$CREATED_EPOCH" ] && [ -n "$NOW" ]; then
    AGE=$((NOW - CREATED_EPOCH))
    if [ "$AGE" -ge 0 ] && [ "$AGE" -le "$MAX_AGE_SECONDS" ]; then
      FRESH=yes
    fi
  fi
fi
if [ -z "$FRESH" ] && [ -z "${CREATED_EPOCH:-}" ]; then
  # timestamp unreadable — judge by modification time instead
  if [ -n "$(find "$SNAPSHOT" -mmin -60 2>/dev/null)" ]; then
    FRESH=yes
  fi
fi
if [ -z "$FRESH" ]; then
  log "skipped stale created=${CREATED:-unknown}"
  retire
  exit 0
fi

# ── 4. same working directory ────────────────────────────────────────────
# Left in place on a mismatch: the session it belongs to may still open.
SNAPSHOT_CWD=$(field cwd)
if [ -n "$SNAPSHOT_CWD" ] && [ "$SNAPSHOT_CWD" != "$SESSION_CWD" ]; then
  log "skipped cwd mismatch snapshot=$SNAPSHOT_CWD session=$SESSION_CWD"
  exit 0
fi

# ── inject ───────────────────────────────────────────────────────────────
printf '%s\n\n' "[REFRESH CONTEXT] 이전 세션이 /refresh로 저장한 스냅샷입니다. 이 내용을 바탕으로 작업을 이어가세요."
cat "$SNAPSHOT"
retire
log "injected ${SIZE}B cwd=$SESSION_CWD"
exit 0
