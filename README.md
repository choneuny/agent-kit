# agent-kit

코딩 에이전트를 배우고·이해하고·결정하는 사람으로 쓰기 위한 묶음. 스킬은 `skills/<이름>/SKILL.md` 한 장이 규칙의 전부이고,
무엇이고 왜 그런지는 [개념 지도](https://choneuny.github.io/agent-kit/agent-concept-maps/)에 그림으로 적었다.
도구 하나(`tools/context-diet`)가 같이 들어 있다.

| 이름 | 무엇 | 정본 |
|---|---|---|
| [`skills/explain-with-pictures`](skills/explain-with-pictures/SKILL.md) | 아무것도 모르는 독자에게 개념 하나를 그림 한 장이 있는 자기완결 HTML로 설명한다 | 유지자의 `.agents` 저장소 |
| [`skills/korean-writing`](skills/korean-writing/SKILL.md) | 한국어 산출물의 문체와 AI 티 금지 목록. 상시 규칙으로 두는 쪽이 맞다 | 같음(규칙 `korean-writing-style.md`) |
| [`skills/docs-and-memory`](skills/docs-and-memory/SKILL.md) | 문서 네 층·티켓·세 통(repo·메모리·소모품)으로 배운 것을 두는 법 | 같음(규칙 `docs/structure.md` + 스킬 `docs-upkeep`) |
| [`skills/agent-concept-maps`](skills/agent-concept-maps/SKILL.md) | 개념 지도를 펼쳐 보이고, 설명받고, 한 장 더 만들고, 다른 주제로 재사용하는 법 | 이 저장소 |
| [`tools/context-diet`](tools/context-diet/SKILL.md) | 세션 컨텍스트에 실리는 것을 재고·실측·판정해 지도 한 장으로 보여 주는 도구(Python + Svelte) | 유지자의 작업 저장소 |

이 저장소는 배포 사본이다. 정본이 바뀌면 여기로 다시 내려온다.

## 설치

```bash
git clone https://github.com/choneuny/agent-kit.git
ln -s "$PWD/agent-kit/skills/explain-with-pictures" ~/.claude/skills/explain-with-pictures
ln -s "$PWD/agent-kit/skills/agent-concept-maps"    ~/.claude/skills/agent-concept-maps
ln -s "$PWD/agent-kit/skills/docs-and-memory"       ~/.claude/skills/docs-and-memory
cp     agent-kit/skills/korean-writing/SKILL.md     ~/.claude/rules/korean-writing.md   # 상시 규칙
```

Codex는 `~/.codex/skills/<이름>`에 같은 링크를 건다. 다른 도구는 프로젝트 `AGENTS.md`에서 해당 `SKILL.md`를 가리킨다.
context-diet는 `tools/context-diet/SKILL.md`의 설치 절을 따른다.
