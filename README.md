# agent-kit

코딩 에이전트를 배우고·이해하고·결정하는 사람으로 쓰기 위한 묶음이다. 항상 걸어 두는 규칙 둘,
필요할 때 불러 쓰는 스킬 셋, 도구 하나가 들어 있다. Claude Code와 Codex 양쪽에 같은 것이 깔린다.
무엇이고 왜 그런지는 [개념 지도](https://choneuny.github.io/agent-kit/agent-concept-maps/)에 그림으로 적었다.

## 설치

```bash
git clone https://github.com/choneuny/agent-kit.git
```

설치는 에이전트에게 [`INSTALL.md`](INSTALL.md)대로 하라고 하면 된다. 어느 하네스가 깔려
있는지 보고 있는 쪽만 건다. 다시 시켜도 결과가 같다. 이름이 같은데 이 저장소가 건 것이 아닌
파일은 손대지 않고 건너뛴다고 알린다. 되돌리는 절도 같은 문서에 있다.

깔리는 자리는 이렇다. macOS와 Linux에서는 이 저장소를 가리키는 심링크라서 저장소를
`git pull`하면 그대로 따라간다. Windows에서는 복사라 당긴 뒤 다시 복사해야 한다.

| 자리 | 무엇 |
|---|---|
| `~/.claude/rules/<이름>.md` | 규칙 둘 |
| `~/.claude/skills/<이름>` | 스킬 셋 |
| `~/.claude/commands/refresh.md` | `/refresh` 명령 |
| `~/.claude/settings.json` | `SessionStart` 훅 한 항목. 없을 때만 더한다. 고치기 전에 `settings.json.bak-<시각>`을 만든다 |
| `~/.codex/skills/<이름>` | 스킬 셋 |
| `~/.codex/AGENTS.md` | 규칙 본문을 `<!-- agent-kit:begin -->`…`end` 블록으로 넣는다. 블록 밖의 글은 손대지 않는다 |
| `~/.codex/hooks.json` | `SessionStart` 훅 한 항목. Claude 쪽과 같은 방식으로 없을 때만 더하고 고치기 전에 백업한다 |

훅은 `refresh` 스킬이 남긴 세션 스냅샷을 새 세션에 넣어 주는 일만 한다. 넣을 것이 없으면
아무 일도 하지 않는다. Claude Code와 Codex가 같은 스크립트를 쓴다. bash가 있으면
`session-start.sh`를, Windows에 Git Bash가 없으면 `session-start.ps1`을 건다.

Codex는 `config.toml`에 `features.hooks`가 켜져 있어야 훅을 돌린다. 남의 TOML을 손대는 것은
위험해서 설치 절차는 그 파일을 읽기만 한다. 안 켜져 있으면 켜라고 한 줄 알린다. 직접
`[features]` 절에 `hooks = true`를 넣으면 된다.

## 구성

| 이름 | 언제 | 무엇 |
|---|---|---|
| [`rules/korean-writing.md`](rules/korean-writing.md) | 늘 실린다 | 한국어 산출물의 문체와 AI 티 금지 목록 |
| [`rules/docs-and-memory.md`](rules/docs-and-memory.md) | 늘 실린다 | 문서 네 층·게이트·티켓·누적 문서를 어디에 두고 어떻게 쌓나 |
| [`skills/docs-upkeep`](skills/docs-upkeep/SKILL.md) | 부를 때 펼친다 | 그 구조에 맞춰 언제 어떤 순서로 정리하나. 배운 것을 저장소·메모리·소모품 셋으로 가르는 기준도 여기 |
| [`skills/refresh`](skills/refresh/SKILL.md) | 부를 때 펼친다 | 세션 스냅샷을 남기고 컨텍스트를 비운 뒤 하던 일을 잇는다 |
| [`skills/explain-with-pictures`](skills/explain-with-pictures/SKILL.md) | 부를 때 펼친다 | 아무것도 모르는 독자에게 개념 하나를 그림 한 장이 있는 자기완결 HTML로 설명한다 |
| [`tools/context-diet`](tools/context-diet/SKILL.md) | 따로 깐다 | 세션마다 컨텍스트에 실리는 것을 재고·실측·판정해 지도 한 장으로 보여 준다 (Python + Svelte) |

context-diet는 Python 환경과 화면 빌드가 따로 필요해서 설치 절차가 걸지 않는다. 쓰려면
[`tools/context-diet/SKILL.md`](tools/context-diet/SKILL.md)의 설치 절을 따른다.

다른 하네스는 프로젝트 `AGENTS.md`에서 해당 `SKILL.md`와 `rules/*.md`를 가리키면 된다.
