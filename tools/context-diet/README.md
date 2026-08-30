# context-diet

에이전트 하네스(우선 Claude Code, 뒤에 Codex·Hermes)가 세션마다 컨텍스트에 싣는 것들 —
규칙·스킬·슬래시 명령·훅·플러그인·MCP 서버·메모리 — 을 한 자리에서 **재고하고, 재고, 판정하고**,
빼기로 한 것을 **되돌릴 수 있는 방식으로 끄는** 도구다. 결과는 웹 화면(Svelte+Vite)의 지도 한 장으로 본다.

## 왜 있나

하네스에 이것저것 들이다 보면 세션 시작부터 수십 k 토큰이 사라지는데, 무엇이 얼마를 먹고
실제로 쓰이는지 한눈에 보이는 곳이 없었다. 2026-08-22 실측으로 MCP 도구 정의 61k(notion 33k),
메모리·규칙 34.5k, 스킬 목록 10k가 매 세션 실리고 있었고, 그 가운데 30일간 한 번도 부르지 않은
것이 태반이었다.

이 도구는 두 축을 지도 한 장에 놓는다.

- **비용** — 항목이 세션마다 차지하는 토큰. 파일 크기로 추정하고 `/context` 실측으로 보정한다.
- **쓰임** — 트랜스크립트에서 센 7일·30일 호출 수와, 에이전트가 본문을 읽고 내린 정성 판정
  (Keep / Improve / Update / Retire / Merge into X)과 그 근거.

## 쓰는 법

```bash
uv sync && (cd ui && npm ci)
uv run scripts/inventory.py                                    # 재고·토큰 추정 → data/inventory.json
uv run scripts/context_parse.py --from-transcript <세션.jsonl>   # /context 실측으로 추정 보정 (새 세션에서 /context 한 번 치고 그 .jsonl)
uv run scripts/usage.py                                        # 7일·30일 호출 수 → data/usage.json
uv run scripts/installed.py                                    # 설치 시각
uv run scripts/map.py                                          # 지도 트리 → data/map.json (화면이 읽는 파일)
cd ui && npm run dev                                           # http://127.0.0.1:5173
```

판정까지 받으려면 `uv run scripts/judge.py` 뒤 `uv run scripts/decisions.py`. 스크립트마다 무엇을 어떻게 세는지는
`docs/guides/measuring.md`, 판정은 `docs/guides/judging.md`. 절차 전체와 재사용법은 [`SKILL.md`](SKILL.md).

화면은 아무것도 끄지 않는다. 노드에 단 메모와 「둔다/뺀다/줄인다」는 `data/decisions-state.json`에 쌓이고, 실제로 끄는 것은
에이전트(또는 사람)가 `docs/guides/disabling.md` 방식으로 되돌릴 수 있는 방식(설정 토글·심링크 해제·`.disabled/` 이동·백업 뒤 수정)으로
처리한 뒤 `data/actions.jsonl`에 적는다. 삭제는 하지 않고 규칙·스킬 정본은 건드리지 않는다.

`data/`는 자기 환경의 재고라 커밋하지 않는다(`.gitignore`). 같이 들어 있는 `data/calibration.json`은 2026-08 실측에서 나온 토큰 추정
계수 둘뿐이고, 자기 환경에서 `context_parse.py`를 돌리면 덮어쓴다.
