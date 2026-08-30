# explain-with-pictures

아무것도 모르는 독자에게 개념 하나를 설명하는 에이전트 스킬. 산출은 **자기완결 HTML 한 장**이다 —
인라인 SVG로 그린 그림과 그 그림을 푸는 산문. 규칙은 [`SKILL.md`](SKILL.md) 한 장이 전부다.

> 이 스킬이 무엇이고 왜 이렇게 짧은지는 [설명 페이지](docs/index.html)에 그림으로 적어 두었다.
> 그 페이지 자체가 이 스킬로 만든 것이다.

## 왜 짧은가

시중 다이어그램 스킬(2만 토큰대)과 지침 없는 판을 포함해 다섯 변주를 같은 조건에서
열다섯 번 돌려 봤다. 결과는 **가장 짧은 원칙 묶음이 세 표본 모두 1위**였고, 픽셀 크기와 서체를
지정한 무거운 규칙이 바닥이었다. 좌표를 손으로 계산시키면 한글이 깨지고, 라벨 상한이 정보를 깎았다.

그래서 이 스킬에는 수치가 없다. 원칙만 있고 값은 그림마다 다시 고른다.

## 쓰는 법

에이전트가 읽을 수 있는 자리에 `explain-with-pictures/SKILL.md`를 둔다.

- **Claude Code** — `~/.claude/skills/explain-with-pictures/`
- **Codex** — `~/.codex/skills/explain-with-pictures/`
- **그 밖** — 프로젝트의 `AGENTS.md`에서 이 파일을 가리킨다

```bash
git clone https://github.com/choneuny/explain-with-pictures.git
ln -s "$PWD/explain-with-pictures" ~/.claude/skills/explain-with-pictures
```

그다음은 평범하게 부탁하면 된다. 「이거 그림으로 설명해 줘」, 「처음 보는 사람용 페이지로 만들어 줘」.

## 받은 그림에서 무엇을 보나

스킬이 그리는 법을 알고 있으니 사람이 할 일은 넷뿐이다.

1. 상자 이름이 내가 쓰는 말인가
2. 화살표가 맞는 쪽을 보나
3. 근거 없는 것이 그려져 있지 않나
4. 내가 아는 것 중 빠진 게 없나

## 함께 쓰면 좋은 것

한국어로 쓴다면 문체를 다듬는 스킬을 뒤에 한 번 통과시킨다. 이 스킬은 무엇을 그리고
무엇을 쓸지를 정하고, 문장을 다듬는 일은 그쪽 몫이다.

## 라이선스

MIT.
