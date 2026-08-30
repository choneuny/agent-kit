# context-diet — 게이트

**정본은 `scripts/`의 코드와 `docs/guides/`의 지침이다.** `data/` 아래는 스크립트가 만드는 산출물이라
손으로 고치지 않고, 고칠 것이 있으면 스크립트를 고친다. 왜 이 도구가 있는지는 `README.md`.

## 지침

| 지침 | 여는 때 |
|---|---|
| `guides/measuring.md` | 재고·추정·실측·호출 수 스크립트를 돌리거나 고칠 때, 숫자가 이상할 때 |
| `guides/judging.md` | 정성 판정을 다시 돌리거나 판정 결과를 읽을 때 |
| `guides/ui-terms.md` | 화면 문구를 쓰거나 고칠 때 |
| `guides/annotations.md` | 사용자가 화면에 단 메모·선택·질문을 읽고 답할 때 |
| `guides/disabling.md` | 판정을 실제로 실행할 때 — 되돌릴 수 있는 끄기 방법과 기록 |


## 절대 규칙

- 끄기는 되돌릴 수 있는 방식만(설정 토글·심링크 해제·`.disabled/` 이동·백업 뒤 수정). 삭제하지 않는다.
  규칙·스킬 정본 `~/.agents`는 어떤 경우에도 건드리지 않는다.
- UI는 끄지 않는다. 주석(`data/decisions-state.json` — 노드별 메모·선택·대화 줄)만 쌓고, 실행은 에이전트가 `guides/annotations.md` 절차로 `data/actions.jsonl`에 기록하며 한다.
- 우리 설정 가운데 한쪽 하네스(CLI / 데스크톱)에만 실리는 것이 있으면 표시할 축이 아니라 **우리 쪽 오류**다. 결함으로 올린다.
- 훅 스크립트 본문 토큰은 컨텍스트 비용이 아니다. 스킬·명령·에이전트는 목록 토큰과 본문 토큰을 합산하지 않는다.
- 표준: Python은 uv(3.12+, 표준 라이브러리 우선), 프런트는 Svelte+Vite. 한국어 문안은 `guides/ui-terms.md`.
- `data/`는 자기 환경의 재고라 커밋하지 않는다(`.gitignore`). 다른 사람 환경의 산출물을 저장소에 넣지 않는다.

## 가지 않아도 되는 곳

`ui/node_modules`, `.venv`, `data/context-samples/`(실측 원문 표본 — 읽기는 하되 고치지 않는다),
`data/judgments/`(판정 묶음 입출력 — `judgments.json`이 병합본).
