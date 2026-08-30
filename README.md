# agent-kit

코딩 에이전트를 배우고·이해하고·결정하는 사람으로 쓰기 위한 스킬 묶음. 스킬마다 `skills/<이름>/SKILL.md` 한 장이 규칙이고,
그 옆 `README.md`가 왜 그 크기인지와 쓰는 법을 적는다. 크기는 전부 같은 조건의 격리 실험으로 정했다 — 무거운 지침이
번번이 졌다.

| 스킬 | 무엇 | 바로 보기 |
|---|---|---|
| [`explain-with-pictures`](skills/explain-with-pictures/) | 아무것도 모르는 독자에게 개념 하나를 그림 한 장이 있는 자기완결 HTML로 설명한다 | [설명 페이지](https://choneuny.github.io/agent-kit/explain-with-pictures/) |
| [`korean-writing`](skills/korean-writing/) | 한국어 문서·보고·README의 문체(해요체)와 AI 티 금지 목록. 상시 규칙으로 두는 쪽이 맞다 | — |
| [`agent-concept-maps`](skills/agent-concept-maps/) | 처음 쓰는 사람을 위한 개념 지도 다섯 장(교재)과 펼치기·설명받기·더 만들기·재사용법 | [지도 차례](https://choneuny.github.io/agent-kit/agent-concept-maps/) |

## 설치

저장소를 받고 쓰고 싶은 스킬 폴더만 에이전트가 읽는 자리에 링크한다.

```bash
git clone https://github.com/choneuny/agent-kit.git
ln -s "$PWD/agent-kit/skills/explain-with-pictures" ~/.claude/skills/explain-with-pictures
ln -s "$PWD/agent-kit/skills/agent-concept-maps"    ~/.claude/skills/agent-concept-maps
cp     agent-kit/skills/korean-writing/SKILL.md     ~/.claude/rules/korean-writing.md   # 상시 규칙
```

Codex는 `~/.codex/skills/<이름>`에 같은 링크를 건다. 다른 도구는 프로젝트 `AGENTS.md`에서 해당 `SKILL.md`를 가리킨다.

## 어디서 왔나

셋 다 diagram-skill-eval 실험 저장소(비공개)에서 나왔다 — 다이어그램 15회, 한국어 규칙 30회의 격리 실행과
블라인드 판정. 실험 기록은 요청하면 보여 준다. 글은 `korean-writing` 규칙으로 썼다.
