---
name: agent-concept-maps
description: 코딩 에이전트를 처음 쓰는 사람에게 개념 지도 여덟 장을 순서대로 펼쳐 보이며 설명하고, 같은 꼴의 장을 더 만들 때 쓴다. 「에이전트가 뭔지 설명해 줘」「개념 지도 보여 줘」「이 지도에 한 장 더」가 방아쇠다.
---

# 에이전트 개념 지도

저장소 루트 `docs/agent-concept-maps/` 아래 장들이 교재다. 뒤 장이 앞 장의 말을 쓴다.

| 장 | 파일 | 답하는 질문 |
|---|---|---|
| 1 | `docs/agent-concept-maps/01-prompt-map.html` | 에이전트에게 매번 무엇이 건네지는가 |
| 2 | `docs/agent-concept-maps/02-coding-agent.html` | 코딩 에이전트란 무엇인가 |
| 3 | `docs/agent-concept-maps/03-context-map.html` | 컨텍스트 지도는 무엇을 보여주는가 |
| 4 | `docs/agent-concept-maps/04-roles.html` | 에이전트와 일할 때 사람이 쥐고 있어야 하는 것 |
| 5 | `docs/agent-concept-maps/05-visual-loop.html` | 왜 그림으로 주고받아야 하나 |
| 6 | `docs/agent-concept-maps/06-writing.html` | 에이전트가 쓴 글은 왜 티가 나나 |
| 7 | `docs/agent-concept-maps/07-docs-and-memory.html` | 배운 것을 어디에 두나 |
| 8 | `docs/agent-concept-maps/08-explain-with-pictures.html` | 설명을 그림 한 장으로 내놓게 하는 규칙 |

## 펼쳐 보이기

- 공개 주소: https://choneuny.github.io/agent-kit/agent-concept-maps/ — 차례 페이지에서 한 장씩 연다.
- 로컬: `docs/agent-concept-maps/index.html`을 브라우저로 연다. 서버가 필요 없다.
- 에이전트가 열어 줄 때: 파일 경로를 `open`(맥)·`xdg-open`(리눅스)·`start`(윈도우)로 열거나, 원격이면 `python3 -m http.server`로 `docs/agent-concept-maps/`를 띄우고 주소를 준다.

## 설명받기

한 장을 읽어 주게 하려면 이렇게 부탁한다 — 「`docs/agent-concept-maps/02-coding-agent.html`을 읽고, 그림을 위에서부터 짚어 가며 처음 보는 사람에게
설명해 줘. 그림에 없는 말은 하지 마.」 에이전트는 HTML 안의 SVG 텍스트와 본문 산문만 근거로 말한다. 독자가 모르는 낱말이
나오면 그 자리에서 「이게 뭐야」를 같은 대화에서 묻게 한다.

여러 장을 이어 볼 때는 장 사이에 「지금까지 이해한 것을 자기 말로」 한 번씩.

## 만들기 — 한 장 더 얹기

같은 꼴의 장은 같은 저장소의 `skills/explain-with-pictures` 스킬로 만든다. 여기 장들과 같은 규약이다.

1. 답할 질문 하나를 제목으로 정한다(위 표처럼 의문문). 한 장에 질문 하나.
2. explain-with-pictures에 그 질문과, 앞 장에서 이미 쓴 낱말 목록을 준다 — 같은 개념을 다른 이름으로 부르지 않게.
3. 나온 HTML을 `docs/agent-concept-maps/09-<주제>.html`로 두고 `docs/agent-concept-maps/index.html` 차례에 한 줄 더한다. 앞 장들의 `nav.back` 링크 형식을 따른다.
4. 브라우저로 열어 넷을 확인한다 — 상자 이름이 내가 쓰는 말인가, 화살표가 맞는 쪽을 보나, 근거 없이 채워 넣은 상자가 없나, 내가 아는 것 중 그림에 빠진 게 없나. 마지막 하나는 사람만 알아볼 수 있다.

## 재사용

- 다른 주제의 교재를 만들 때는 `docs/agent-concept-maps/`를 통째로 복사해 장만 갈아 끼운다. 스타일·차례 페이지는 그대로 쓴다.
- 장 하나만 가져갈 때는 그 HTML 파일 하나면 된다.
- 문장은 같은 저장소의 `skills/korean-writing` 규칙을 따른다. 해요체이고,
  「합니다」가 조금 섞이는 정도는 그대로 둔다.
