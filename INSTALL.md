# 설치 지침

에이전트가 읽고 그대로 실행하는 절차다. 아래에서 `<REPO>`는 이 저장소를 내려받은 절대
경로이고, `<HOOK>`은 3장에서 정하는 훅 실행 명령이다.

## 0. 준비

### 0-1. 저장소 경로를 잡는다

```
cd <저장소> && pwd
```

이 값이 `<REPO>`다. 아래 모든 경로에 이 값을 그대로 넣는다.

### 0-2. 어느 하네스가 있는지 본다

| 하네스 | 있는지 보는 곳 |
|---|---|
| Claude Code | `~/.claude` |
| Codex | `~/.codex` — ChatGPT 데스크톱 앱 안의 Codex와 `codex` CLI가 이 디렉터리를 같이 읽는다 |

디렉터리가 있는 쪽만 설치한다. 없는 쪽은 만들지 않고 건너뛴다. 둘 다 없으면 어느 하네스를
쓰는지 사용자에게 묻고 멈춘다.

### 0-3. 잇는 방식을 고른다

- macOS·Linux: 심링크로 건다. 저장소를 `git pull`하면 걸린 것이 그대로 따라간다.
- Windows: 복사한다. 심링크는 개발자 모드나 관리자 권한이 있어야 만들어진다. 복사로 깔았으면
  저장소를 `git pull`한 뒤 같은 파일을 다시 복사해야 반영된다.

### 0-4. 거는 것의 목록

- 규칙 둘 — `rules/korean-writing.md`, `rules/docs-and-memory.md`
- 스킬 셋 — `skills/explain-with-pictures`, `skills/docs-upkeep`, `skills/refresh`
- `/refresh` 명령 하나 — `skills/refresh/refresh.md`
- `SessionStart` 훅 하나 — `skills/refresh/hooks/`의 스크립트

`tools/context-diet`는 Python 환경과 화면 빌드가 따로 필요해서 이 절차가 걸지 않는다. 쓰려면
`tools/context-diet/SKILL.md`의 설치 절을 따른다.

### 0-5. 이미 있는 파일은 손대지 않는다

거는 자리에 이 저장소가 만든 것이 아닌 파일이나 디렉터리가 이미 있으면 덮어쓰지 않고
건너뛴 뒤, 무엇을 건너뛰었는지 사용자에게 알린다. JSON·Markdown을 고치기 전에는 언제나
같은 자리에 `<파일>.bak-<YYYYMMDDTHHMMSS>` 백업을 먼저 만든다.

## 1. Claude Code

`~/.claude`가 있을 때만 한다.

### 1-1. 규칙 둘

`~/.claude/rules/`를 만들고 규칙 파일 둘을 건다.

macOS·Linux:

```
mkdir -p ~/.claude/rules
ln -s <REPO>/rules/korean-writing.md   ~/.claude/rules/korean-writing.md
ln -s <REPO>/rules/docs-and-memory.md  ~/.claude/rules/docs-and-memory.md
```

Windows(PowerShell):

```
New-Item -ItemType Directory -Force ~/.claude/rules
Copy-Item <REPO>/rules/korean-writing.md   ~/.claude/rules/ -Force
Copy-Item <REPO>/rules/docs-and-memory.md  ~/.claude/rules/ -Force
```

### 1-2. 스킬 셋

디렉터리 통째로 건다.

macOS·Linux:

```
mkdir -p ~/.claude/skills
ln -s <REPO>/skills/explain-with-pictures ~/.claude/skills/explain-with-pictures
ln -s <REPO>/skills/docs-upkeep           ~/.claude/skills/docs-upkeep
ln -s <REPO>/skills/refresh               ~/.claude/skills/refresh
```

Windows(PowerShell):

```
New-Item -ItemType Directory -Force ~/.claude/skills
Copy-Item <REPO>/skills/explain-with-pictures ~/.claude/skills/ -Recurse -Force
Copy-Item <REPO>/skills/docs-upkeep           ~/.claude/skills/ -Recurse -Force
Copy-Item <REPO>/skills/refresh               ~/.claude/skills/ -Recurse -Force
```

### 1-3. `/refresh` 명령

macOS·Linux:

```
mkdir -p ~/.claude/commands
ln -s <REPO>/skills/refresh/refresh.md ~/.claude/commands/refresh.md
```

Windows(PowerShell):

```
New-Item -ItemType Directory -Force ~/.claude/commands
Copy-Item <REPO>/skills/refresh/refresh.md ~/.claude/commands/ -Force
```

### 1-4. `~/.claude/settings.json`에 훅 한 항목

`hooks.SessionStart` 배열에 아래 항목을 **없을 때만** 더한다. 이미 `command`가
`session-start.sh` 또는 `session-start.ps1`로 끝나는 항목이 있으면 아무것도 하지 않는다.

```json
{
  "hooks": [
    { "type": "command", "command": "<HOOK>" }
  ]
}
```

넣는 자리를 통째로 보이면 이렇다. 파일에 다른 설정이 이미 있으면 그것들은 그대로 두고
`hooks.SessionStart`만 손댄다.

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "<HOOK>" } ] }
    ]
  }
}
```

절차:

1. 파일이 없으면 `{}`에서 시작한다.
2. 파일이 있으면 JSON으로 읽는다. 읽히지 않으면 고치지 말고, 파일이 깨졌다고 알린 뒤 이
   단계를 건너뛴다.
3. 고치기 전에 `~/.claude/settings.json.bak-<YYYYMMDDTHHMMSS>`로 백업한다.
4. `hooks.SessionStart`가 없으면 빈 배열로 만들고 위 항목을 넣는다. 들여쓰기 두 칸,
   한글은 이스케이프하지 않고 그대로 쓴다.

## 2. Codex

`~/.codex`가 있을 때만 한다.

### 2-1. 스킬 셋

Claude Code 쪽과 같은 스킬 셋을 `~/.codex/skills/` 아래에 건다.

macOS·Linux:

```
mkdir -p ~/.codex/skills
ln -s <REPO>/skills/explain-with-pictures ~/.codex/skills/explain-with-pictures
ln -s <REPO>/skills/docs-upkeep           ~/.codex/skills/docs-upkeep
ln -s <REPO>/skills/refresh               ~/.codex/skills/refresh
```

Windows(PowerShell):

```
New-Item -ItemType Directory -Force ~/.codex/skills
Copy-Item <REPO>/skills/explain-with-pictures ~/.codex/skills/ -Recurse -Force
Copy-Item <REPO>/skills/docs-upkeep           ~/.codex/skills/ -Recurse -Force
Copy-Item <REPO>/skills/refresh               ~/.codex/skills/ -Recurse -Force
```

### 2-2. `~/.codex/AGENTS.md`에 규칙 블록

Codex의 `AGENTS.md`에는 다른 파일을 끌어오는 문법이 없어서 규칙 본문을 넣는다. 넣는 형태는
이렇다.

```
<!-- agent-kit:begin -->
<!-- agent-kit installs this block. Edit the repo, then redo this step. -->

(rules/korean-writing.md 본문)

(rules/docs-and-memory.md 본문)
<!-- agent-kit:end -->
```

규칙:

- 두 규칙 파일의 맨 앞 YAML frontmatter(첫 줄 `---`부터 다음 `---`까지)는 넣지 않는다.
  하네스 메타데이터라 본문이 아니다.
- 파일에 `<!-- agent-kit:begin -->`이 이미 있으면 `<!-- agent-kit:end -->`까지를 통째로
  새 블록으로 갈아 끼운다.
- 블록 밖의 글은 한 글자도 손대지 않는다.
- 파일이 없으면 새로 만든다. 있으면 끝의 빈 줄을 정리하고 한 줄 띄운 뒤 블록을 붙인다.
- 고치기 전에 `~/.codex/AGENTS.md.bak-<YYYYMMDDTHHMMSS>`로 백업한다.
- 새로 만든 블록이 이미 있던 것과 같으면 파일을 건드리지 않는다.

### 2-3. `~/.codex/hooks.json`에 훅 한 항목

Claude Code 쪽과 같은 훅이지만 `matcher`와 `timeout`이 붙는다. `hooks.SessionStart` 배열에
**없을 때만** 더한다.

```json
{
  "matcher": "startup|resume|clear|compact",
  "hooks": [
    { "type": "command", "command": "<HOOK>", "timeout": 5 }
  ]
}
```

파일 전체로는 이렇다.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [ { "type": "command", "command": "<HOOK>", "timeout": 5 } ]
      }
    ]
  }
}
```

절차는 1-4와 같다. 파일이 없으면 `{}`에서 시작하고, JSON이 깨졌으면 고치지 않고 알리고,
고치기 전에 `~/.codex/hooks.json.bak-<YYYYMMDDTHHMMSS>`로 백업한다.

### 2-4. `~/.codex/config.toml` 확인

Codex는 `config.toml`에 아래가 있어야 훅을 돌린다.

```toml
[features]
hooks = true
```

이 파일은 **읽기만 한다.** 남의 TOML을 고치는 것은 위험하다. 없거나 꺼져 있으면 위 두 줄을
직접 넣으라고 사용자에게 한 줄 알린다.

## 3. 훅 스크립트와 `<HOOK>` 값

훅은 `refresh` 스킬이 남긴 세션 스냅샷(`~/.agent-kit/refresh-snapshot.md`)을 새 세션에 넣어
주는 일만 한다. 넣을 것이 없으면 아무 일도 하지 않는다.

| 환경 | `<HOOK>`에 넣을 값 |
|---|---|
| macOS·Linux | `<REPO>/skills/refresh/hooks/session-start.sh` |
| Windows + Git Bash | `bash <REPO>/skills/refresh/hooks/session-start.sh` |
| Windows, Git Bash 없음 | `powershell -NoProfile -ExecutionPolicy Bypass -File <REPO>/skills/refresh/hooks/session-start.ps1` |

Git Bash가 있는지는 `C:\Program Files\Git\bin\bash.exe`가 있는지로 본다.

macOS·Linux에서는 스크립트에 실행 권한이 있어야 한다.

```
chmod +x <REPO>/skills/refresh/hooks/session-start.sh
```

JSON 문자열 안의 경로는 슬래시(`/`)로 쓴다. 역슬래시를 쓰면 `\\`로 두 번 적어야 한다.
저장소를 복사가 아니라 원래 자리에서 참조하므로, 저장소를 옮기면 이 값을 고쳐야 한다.

두 스크립트는 같은 일을 하고 조건도 같다. 스냅샷 파일이 있고, 64KB 이하이고, `created:`가
한 시간 이내이고, `cwd:`가 세션이 시작한 디렉터리와 같을 때만 본문을 stdout으로 내보낸 뒤
파일을 `refresh-snapshot.consumed`로 옮긴다. 세션이 시작한 디렉터리는 하네스가 stdin으로
주는 JSON의 `cwd`에서 읽고, 없으면 현재 디렉터리로 본다. 어느 갈래에서도 종료 코드는 0이다.

## 4. 확인

설치를 끝낸 뒤 스스로 검사한다.

### 4-1. 파일이 제자리에 있나

```
ls -l ~/.claude/rules/korean-writing.md ~/.claude/rules/docs-and-memory.md
ls -l ~/.claude/skills/explain-with-pictures ~/.claude/skills/docs-upkeep ~/.claude/skills/refresh
ls -l ~/.claude/commands/refresh.md
ls -l ~/.codex/skills/explain-with-pictures ~/.codex/skills/docs-upkeep ~/.codex/skills/refresh
```

Windows(PowerShell)에서는 `Get-ChildItem`을 같은 경로에 쓴다. 설치한 쪽만 본다.

### 4-2. JSON이 성한가

```
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo ok
python3 -m json.tool ~/.codex/hooks.json     > /dev/null && echo ok
```

`python3`이 없으면 `node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))"`을
쓴다.

### 4-3. 훅 항목이 있나

```
grep -c session-start ~/.claude/settings.json
grep -c session-start ~/.codex/hooks.json
```

각각 1 이상이어야 한다. 2 이상이면 항목이 겹쳐 들어간 것이니 하나만 남긴다.

### 4-4. 규칙 블록이 들어갔나

```
grep -c 'agent-kit:begin' ~/.codex/AGENTS.md
```

1이어야 한다.

### 4-5. 훅이 실제로 도는가

가짜 스냅샷을 하나 만들어 훅을 직접 부른다.

```
mkdir -p ~/.agent-kit
printf -- '---\ncreated: %s\ncwd: %s\n---\n\n확인용\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$PWD" > ~/.agent-kit/refresh-snapshot.md
echo "{\"cwd\":\"$PWD\"}" | <HOOK>
```

스냅샷 본문이 그대로 나오고 `~/.agent-kit/refresh-snapshot.consumed`가 생기면 정상이다.
확인이 끝나면 `refresh-snapshot.consumed`는 지워도 된다.

새 세션을 열어야 설치한 것이 실린다.

## 5. 되돌리기

건 것을 지우면 끝난다. 이 저장소가 만들지 않은 파일은 지우지 않는다.

- `~/.claude/rules/korean-writing.md`, `~/.claude/rules/docs-and-memory.md`
- `~/.claude/skills/explain-with-pictures`, `~/.claude/skills/docs-upkeep`, `~/.claude/skills/refresh`
- `~/.claude/commands/refresh.md`
- `~/.codex/skills/explain-with-pictures`, `~/.codex/skills/docs-upkeep`, `~/.codex/skills/refresh`
- `~/.claude/settings.json`과 `~/.codex/hooks.json`에서 `hooks.SessionStart`의 그 항목 하나.
  배열이 비면 `SessionStart` 키를, `hooks`가 비면 `hooks` 키를 지운다
- `~/.codex/AGENTS.md`에서 `<!-- agent-kit:begin -->`부터 `<!-- agent-kit:end -->`까지

심링크로 걸었으면 링크만 지운다. 저장소는 그대로 남는다. `.bak-<시각>` 백업은 지우지 않고
남겨 둔다. `~/.agent-kit`에는 스냅샷과 로그만 있으므로 지워도 되고 두어도 된다.
