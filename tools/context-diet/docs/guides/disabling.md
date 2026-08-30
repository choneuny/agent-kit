# 끄기 지침

범위: 「뺀다/줄인다」 판정을 실제로 실행하는 방법과 기록.
여는 때: 사용자가 「실행해라」고 한 뒤, 항목을 실제로 끌 때.
다루지 않는 것: 판정 자체(`guides/judging.md`), 화면의 메모·선택(`guides/annotations.md`).
전제: 전부 되돌릴 수 있는 방식이고 삭제는 없다. 규칙·스킬 정본 디렉터리는 어떤 경우에도 손대지 않는다.

| 종류 | 끄기 | 되돌리기 |
|---|---|---|
| 규칙 | `~/.claude/rules/<이름>.md` 심링크를 `~/.claude/rules/.disabled/`로 옮긴다 | 심링크를 제자리로 |
| 스킬(개인) | `~/.claude/skills/<이름>` 심링크를 `.disabled/`로 옮긴다 | 같음 |
| 스킬(플러그인) | 개별로 못 끈다 — 플러그인 단위로만. 그 플러그인 행에서 처리한다 | – |
| 명령 | `~/.claude/commands/<이름>.md`를 `~/.claude/commands/.disabled/`로 옮긴다 | 파일을 제자리로 |
| 에이전트 | `~/.claude/agents/`에서 `.disabled/`로 옮긴다 | 같음 |
| 훅 | `settings.json`의 해당 hook 항목을 제거한다 | 백업에서 복원 |
| MCP | `~/.claude.json`의 `mcpServers`에서 그 서버를 `disabledMcpServers` 쪽으로 옮긴다 | 되돌림 |
| 플러그인 | `settings.json`의 `enabledPlugins`에서 `<플러그인>@<마켓>`을 false | 다시 true |
| 메모리 | 불가. CLAUDE.md·AGENTS.md는 cwd에서 자동으로 읽히므로 「줄여라」 안내만 | – |
| 내장 MCP·시스템 도구 | 불가. 사유 표시만 | – |

설정 파일을 고칠 때는 같은 디렉터리에 `settings.json.bak-<시각>`을 먼저 만든다. 한 일은 `data/actions.jsonl`에 한 줄씩 —
시각, 항목(kind·name·path), 동작, 건드린 파일, 되돌리는 명령 한 줄.

`disabledMcpServers`가 실제로 먹히는지는 미확인이다. 안 먹으면 서버 정의를 `mcpServers` 밖의 보관 키로 옮긴다.
