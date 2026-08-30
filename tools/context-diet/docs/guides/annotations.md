# 주석 읽고 답하기 지침

범위: 화면에서 사용자가 노드에 단 메모·선택·질문(`data/decisions-state.json`)을 에이전트가 읽고 답하고 실행하는 절차.
여는 때: 사용자가 「주석 봐라」고 하거나, 세션을 시작해 이 프로젝트에 들어왔을 때.
다루지 않는 것: 끄기의 실제 방법(`guides/disabling.md`), 지도 데이터 생성(`guides/measuring.md`).
전제: UI는 끄지 않는다. 파일에 의도만 쌓이고, 실행과 답은 에이전트 몫이다.

## 파일

`data/decisions-state.json` = `{ [노드 id]: { choice, memo, updated_at, thread:[{by:"user"|"agent", at, text}] } }`. 노드 id는 `data/map.json`의 것(`mcp:notion`, `rule:docs-and-memory`, `skill:debate`, `mcp_tool:notion:notion-search` …). choice는 `keep|remove|shrink|hold|merge:<이름>|null`.

## 절차

1. 파일을 읽어 `thread`의 마지막이 `by:"user"`인 노드를 모은다 — 답을 기다리는 질문이다. 메모만 있고 질문이 아니면 답하지 않는다.
2. 답은 그 노드의 재료(`decisions.json` 카드·`summaries.json`·`judgments.json`)와 실물(파일·설정·트랜스크립트)로 쓰고, `thread`에 `{by:"agent", at, text}`로 append한다. 한국어, 짧게, 근거 포함. 파일을 통째로 다시 쓰지 말고 해당 노드만 고친다.
3. `choice`가 `remove|shrink|merge:*`인 노드는 실행 후보다. 실행은 사용자가 「실행해라」고 한 뒤에만, `guides/disabling.md` 방식(되돌릴 수 있게, 백업 먼저)으로 하고 `data/actions.jsonl`에 한 줄(`{at, id, choice, did, undo}`)을 적는다. 실행 뒤 `thread`에 무엇을 했는지 append.
4. 사용자가 답을 바로 보려면 화면을 다시 열거나 창 포커스를 주면 된다(UI가 그때 파일을 다시 읽는다).
