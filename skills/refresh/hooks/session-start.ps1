#!/usr/bin/env pwsh
# agent-kit / refresh - SessionStart hook, PowerShell edition.
#
# Same job as session-start.sh, for Windows hosts without Git Bash.
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
# On success the snapshot body goes to stdout - a SessionStart hook's stdout
# goes into the session context. Every path exits 0; a broken snapshot must
# never break a session.
#
# Windows PowerShell 5.1 and PowerShell 7 both run this.

$ErrorActionPreference = 'SilentlyContinue'

$kitDir = if ($env:AGENT_KIT_STATE_DIR) { $env:AGENT_KIT_STATE_DIR } else { Join-Path $HOME '.agent-kit' }
$snapshot = Join-Path $kitDir 'refresh-snapshot.md'
$consumed = Join-Path $kitDir 'refresh-snapshot.consumed'
$logFile  = Join-Path $kitDir 'refresh.log'
$maxBytes = 65536
$maxAgeSeconds = 3600

function Write-KitLog([string]$message) {
  if (-not (Test-Path -LiteralPath $kitDir)) { return }
  $stamp = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
  $line = "{0}`t{1}`r`n" -f $stamp, $message
  try { [IO.File]::AppendAllText($logFile, $line, (New-Object Text.UTF8Encoding $false)) } catch { }
}

function Retire-Snapshot {
  try { Move-Item -LiteralPath $snapshot -Destination $consumed -Force } catch { }
}

function Get-Field([string]$name, [string[]]$lines) {
  foreach ($line in $lines) {
    if ($line -match ("^{0}:\s*(.*)$" -f [regex]::Escape($name))) {
      return $Matches[1].Trim().Trim('"').Trim()
    }
  }
  return ''
}

function Normalize-Path([string]$path) {
  if (-not $path) { return '' }
  $p = $path.Trim().Replace('\', '/')
  while ($p.Length -gt 1 -and $p.EndsWith('/')) { $p = $p.Substring(0, $p.Length - 1) }
  return $p
}

if (-not (Test-Path -LiteralPath $snapshot -PathType Leaf)) { exit 0 }

# -- the directory this session started in --------------------------------
# The harness feeds the hook a JSON object on stdin that carries "cwd".
# Read it only when stdin is redirected, and fall back to the process
# working directory.
$sessionCwd = ''
if ([Console]::IsInputRedirected) {
  $hookInput = ''
  try { $hookInput = [Console]::In.ReadToEnd() } catch { $hookInput = '' }
  if ($hookInput -match '"cwd"\s*:\s*"([^"]*)"') {
    $sessionCwd = $Matches[1] -replace '\\\\', '\'
  }
}
if (-not $sessionCwd) { $sessionCwd = (Get-Location).Path }

# -- 2. size --------------------------------------------------------------
$item = Get-Item -LiteralPath $snapshot
$size = [int64]$item.Length
if ($size -gt $maxBytes) {
  Write-KitLog ("skipped oversize {0}B" -f $size)
  Retire-Snapshot
  exit 0
}

$lines = @()
try { $lines = Get-Content -LiteralPath $snapshot -Encoding utf8 } catch { $lines = @() }

# -- 3. freshness ---------------------------------------------------------
# Prefer the declared `created:` stamp; fall back to file mtime when it
# cannot be parsed, so a hand-written snapshot still works.
$created = Get-Field 'created' $lines
$fresh = $false
$parsed = $null
if ($created) {
  try { $parsed = [DateTimeOffset]::Parse($created, [Globalization.CultureInfo]::InvariantCulture) } catch { $parsed = $null }
}
if ($parsed -ne $null) {
  $age = ([DateTimeOffset]::Now - $parsed).TotalSeconds
  if ($age -ge 0 -and $age -le $maxAgeSeconds) { $fresh = $true }
} else {
  $age = ([DateTime]::Now - $item.LastWriteTime).TotalSeconds
  if ($age -ge 0 -and $age -le $maxAgeSeconds) { $fresh = $true }
}
if (-not $fresh) {
  $shown = if ($created) { $created } else { 'unknown' }
  Write-KitLog ("skipped stale created={0}" -f $shown)
  Retire-Snapshot
  exit 0
}

# -- 4. same working directory --------------------------------------------
# Left in place on a mismatch: the session it belongs to may still open.
$snapshotCwd = Get-Field 'cwd' $lines
if ($snapshotCwd -and ((Normalize-Path $snapshotCwd) -ne (Normalize-Path $sessionCwd))) {
  Write-KitLog ("skipped cwd mismatch snapshot={0} session={1}" -f $snapshotCwd, $sessionCwd)
  exit 0
}

# -- inject ---------------------------------------------------------------
$header = '[REFRESH CONTEXT] 이전 세션이 /refresh로 저장한 스냅샷입니다. 이 내용을 바탕으로 작업을 이어가세요.'
try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }
Write-Output $header
Write-Output ''
foreach ($line in $lines) { Write-Output $line }
Retire-Snapshot
Write-KitLog ("injected {0}B cwd={1}" -f $size, $sessionCwd)
exit 0
