---
name: refresh
description: Save a lightweight session snapshot from live context, then guide user to /clear or /compact for a fresh context window with automatic resume.
---

# Refresh Command

컨텍스트 윈도우를 리프레시하면서 세션 연속성을 유지한다. Claude가 현재 대화 컨텍스트에서 직접 스냅샷을 생성하고, `/clear` 또는 `/compact` 후 자동으로 주입한다.

## Process

### Step 0: 문서 마감부터 (docs-upkeep)

스냅샷은 세션 마무리의 **마지막** 걸음이다. 먼저 `docs-upkeep` 스킬을 불러 이 세션이
만든 판정·규칙·경위가 repo 문서(원장·지침·티켓·CHANGELOG)와 메모리에 실렸는지
점검하고 채운다. 압축되면 문서에 안 실린 지식은 사라진다 — 스냅샷만 쓰고 끝내는
것은 절반이다.

### Step 1: Generate Snapshot

현재 대화 컨텍스트를 기반으로 아래 포맷의 스냅샷을 작성한다. 외부 파일이나 transcript를 읽지 않는다 — 지금 컨텍스트 윈도우에 있는 정보만 사용.

2KB 이내로 간결하게. 코드 블록 금지. 파일 경로와 기술 용어는 영문, 나머지는 한국어.

```markdown
---
type: refresh-snapshot
created: YYYY-MM-DDTHH:MM:SS+09:00
session_id: <Bash로 획득 — 아래 정확한 명령 참조>
project: <canonical project stem>
cwd: <current working directory>
---

## 목표

[이 세션에서 하고 있는 일. 1-2문장.]

## 현재 상태

[지금 어디까지 왔는지. 완료/진행중/미시작 항목.]

| 파일 | 상태 | 비고 |
|------|------|------|
| `path` | ✅/🔄/❌ | 한줄 설명 |

## 결정 사항

- **[결정]** — 근거: [이유]

## 실패한 시도

- **[시도]** — 원인: [왜 실패했는지]

## 미해결

- [열린 질문이나 블로커]

## 다음 스텝

[resume 후 바로 할 일. 구체적으로.]

## 참고 가이드

[Step 1.5에서 상세 가이드를 작성한 경우에만 이 섹션을 포함. 없으면 통째로 생략.]
**resume 직후, 작업을 재개하기 전에 아래 가이드를 먼저 읽는다.**

- @<가이드 절대경로> — [한줄 설명]
```

### Step 1.5: (선택) 상세 가이드 작성

스냅샷은 2KB 경량 요약이라 긴 작업 흐름·코드 스니펫·명령 시퀀스·디버깅 기록처럼 부피가 큰 디테일은 담을 수 없다. 이런 정보가 resume 후 작업을 이어가는 데 의미 있게 도움이 되겠다고 판단되면, 별도 가이드 파일을 작성하고 스냅샷에서 링크한다. 작성 여부·범위·분량은 현재 작업의 성격을 보고 **스스로 판단한다** — 정해진 트리거 목록은 없다. 보존할 디테일이 없으면 이 스텝은 건너뛴다. 명령 시퀀스, 코드·diff, 디버깅 가설/로그, 다단계 변경 계획 등이 흔한 후보지만 거기에 국한되지 않는다.

작성 방법:
- 저장 위치: 현재 프로젝트(cwd) 기준 로컬 — `<cwd>/.refresh-guides/<YYYY-MM-DD-HHMM>-<slug>.md`. Write tool로 작성하고, 디렉토리가 없으면 `mkdir -p`로 먼저 생성
- 형식:
  ```markdown
  ---
  type: refresh-guide
  created: YYYY-MM-DDTHH:MM:SS+09:00
  snapshot: refresh-snapshot.md
  ---

  ## [주제]

  [스냅샷에 담기지 않은 상세. 코드 블록·명령·로그·diff 허용. 분량 제한 없음.]
  ```
- 작성한 가이드를 스냅샷의 `## 참고 가이드` 섹션에 **@링크 형식**(`@<가이드 절대경로>`)으로 적고, "resume 직후 먼저 읽으라"는 지시 문장을 함께 넣는다. 절대경로를 쓴다 — resume 시점의 cwd가 같아도 @링크 해석을 확실히 하기 위함.
- 두 장치는 역할이 다르다: @링크는 resume 시 해당 파일을 컨텍스트로 끌어오고, 명시적 "먼저 읽어라" 지시는 작업 재개 전에 그 가이드를 반드시 참고하게 만든다. 둘 다 넣는다.
- 주의: 이 가이드는 SessionStart에서 **자동 주입되지 않는다.** 자동 주입되는 건 `refresh-snapshot.md` 하나뿐이고, 가이드는 스냅샷의 @링크와 읽기 지시를 통해 resume 시 끌어와 읽는다.

### Step 2: Write Snapshot File

스냅샷을 마커 파일 위치에 바로 쓴다. 디렉터리가 없으면 먼저 만든다:

```bash
mkdir -p ~/.agent-kit
```

파일 경로는 `~/.agent-kit/refresh-snapshot.md`.

### Step 3: Guide User

스냅샷 내용을 출력한 뒤, 다음 메시지를 표시한다. 상세 가이드(Step 1.5)를 작성했다면 그 경로 줄도 함께 보여주고, 작성하지 않았으면 해당 줄은 생략한다.

```
---
✓ Snapshot saved (N bytes)
✓ Detail guide: <경로>   ← 작성한 경우에만 표시

/clear 또는 /compact을 입력하면 컨텍스트가 리프레시되고, 위 스냅샷이 자동으로 주입됩니다.
  · /clear   — 컨텍스트를 완전히 비운 뒤 스냅샷만 주입 (가장 깔끔, 권장)
  · /compact — 기존 대화 요약 위에 스냅샷을 덧붙임 (요약과 일부 중복 가능)
```

## Notes

- **session_id는 transcript 파일명에서 획득한다(Claude Code 기준).** 아래 Bash 명령으로 현재 cwd의 최신 transcript를 찾아 파일명(= session_id)을 추출한다. 명령이 아무것도 내놓지 않는 하네스에서는 `session_id`를 비워 둔다 — 주입 조건에 쓰이지 않는다:
  ```
  ENCODED_CWD=$(printf '%s' "$PWD" | sed 's|^/||; s|/|-|g')
  ls -t "$HOME/.claude/projects/-${ENCODED_CWD}/"*.jsonl 2>/dev/null | head -1 | xargs basename | sed 's/\.jsonl$//'
  ```
  병렬 세션이 덮어쓸 수 있는 상태 파일은 쓰지 않는다. ndjson 파싱, system-reminder 추측도 금지
- 스냅샷 주입은 SessionStart hook(`hooks/session-start.sh`)이 담당하며 이벤트 종류(startup/clear/compact)를 가리지 않음 — 파일이 64KB 이하·1시간 이내·동일 cwd 조건만 충족하면 `/clear`든 `/compact`든 동일하게 주입됨. 훅은 스냅샷 본문을 **stdout**으로 내보내고(SessionStart 훅의 stdout이 세션 컨텍스트로 들어간다), 주입 뒤 파일을 `refresh-snapshot.consumed`로 옮겨 두 번 들어가지 않게 한다
- 훅이 걸리는 자리는 하네스마다 다르다. Claude Code는 `~/.claude/settings.json`의 `hooks.SessionStart`, Codex는 `~/.codex/hooks.json`의 같은 자리(matcher `startup|resume|clear|compact`)다. Codex는 `config.toml`의 `features.hooks`가 켜져 있어야 훅을 돌린다. 둘 다 저장소 루트의 `INSTALL.md` 절차가 걸어 준다. 훅 스크립트는 bash판 `hooks/session-start.sh`와 같은 일을 하는 PowerShell판 `hooks/session-start.ps1`이 있고, Windows에 Git Bash가 없으면 후자를 건다
- `/clear`와 `/compact`의 차이는 컨텍스트 처리 방식(완전 비움 vs 요약 유지)임
- 이 스냅샷은 즉시 resume용 경량 요약이며, 세션 전체 기록을 대체하지 않음
- 상세 가이드(Step 1.5)는 자동 주입 대상이 아님 — 스냅샷의 링크를 통해서만 접근. 가이드 파일은 현재 프로젝트의 `.refresh-guides/`에 누적되며 자동 정리되지 않음 (필요 시 `.gitignore`에 추가 권장)
- Compaction이 많이 발생한 세션에서는 이미 손실된 정보는 복구 불가 — 가능한 한 일찍 `/refresh` 호출 권장
