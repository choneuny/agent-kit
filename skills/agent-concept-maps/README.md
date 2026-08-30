# agent-concept-maps

코딩 에이전트를 처음 쓰는 사람을 위한 개념 지도 다섯 장. 그림 한 장과 그것을 푸는 글이 한 페이지씩이고, 순서대로 읽으면
한 시간이 안 걸린다. **바로 보기: https://choneuny.github.io/agent-kit/agent-concept-maps/**

1. 에이전트에게 매번 무엇이 건네지는가
2. 코딩 에이전트란 무엇인가
3. 컨텍스트 지도는 무엇을 보여주는가
4. 에이전트와 일할 때 사람이 쥐고 있어야 하는 것
5. 왜 그림으로 주고받아야 하나

## 왜 있나

에이전트를 가르칠 때 남는 것은 도구 설정이 아니라 「무엇을 물어볼지 아는 것」이다. 그 감각을 심으려면 안에서 무슨 일이
일어나는지를 그림으로 한 번 보는 게 가장 빠르다. 다섯 장은 그 목적으로 같은 저장소의 `skills/explain-with-pictures`
스킬로 만들었고, 각 장은 외부 의존 없이 혼자 열리는 HTML이다.

## 쓰는 법

[`SKILL.md`](SKILL.md)에 넷을 적어 두었다 — 펼쳐 보이기, 에이전트에게 설명받기, 같은 꼴의 장을 더 만들기, 다른 주제로 재사용하기.
에이전트가 읽을 자리에 두려면:

```bash
git clone https://github.com/choneuny/agent-kit.git
ln -s "$PWD/agent-kit/skills/agent-concept-maps" ~/.claude/skills/agent-concept-maps   # Codex는 ~/.codex/skills/
```

그다음 「에이전트가 뭔지 그림으로 설명해 줘」라고 부탁하면 에이전트가 이 장들을 순서대로 펼친다.

## 만든 것

- 각 장: 자기완결 HTML + 인라인 SVG, Noto Sans KR(Google Fonts)만 외부에서 온다.
- 글은 같은 저장소의 `skills/korean-writing` 규칙으로 썼다.
