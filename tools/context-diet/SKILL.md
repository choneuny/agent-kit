---
name: context-diet
description: 에이전트 하네스(Claude Code 우선)가 세션마다 컨텍스트에 싣는 규칙·스킬·훅·플러그인·MCP·메모리를 재고하고, 토큰을 재고, 30일 쓰임을 세고, 둘지 뺄지 판정 재료를 지도 한 장으로 보여 주는 도구. 「세션이 왜 이렇게 무겁지」「뭘 끄면 되지」「컨텍스트 지도 띄워 줘」가 방아쇠다.
---

# context-diet

세션 컨텍스트 117k 가운데 무엇이 얼마를 먹고 실제로 쓰이는지를 한 장의 지도로 본다. 스크립트가 `data/`에 산출물을 쓰고,
Svelte 화면이 그것을 읽는다. 정본은 `scripts/`와 `docs/`이고 `data/`는 산출물이라 손으로 고치지 않는다.

## 설치

```bash
git clone https://github.com/choneuny/agent-kit.git && cd agent-kit/tools/context-diet
uv sync                      # Python 3.12+, 표준 라이브러리만 쓴다
cd ui && npm ci && cd ..     # 화면
```

## 재기 — 순서대로 넷

```bash
uv run scripts/inventory.py                                    # 재고와 토큰 추정 → data/inventory.json
uv run scripts/context_parse.py --from-transcript <세션.jsonl>   # /context 실측을 읽어 추정을 보정 → data/context-measured.json, calibration.json
uv run scripts/usage.py                                        # 7일·30일 호출 수 → data/usage.json
uv run scripts/installed.py                                    # 설치 시각 → data/installed.json
uv run scripts/map.py                                          # 지도 트리 → data/map.json
```

실측 표본은 새 세션에서 `/context`를 한 번 치고 그 세션의 `.jsonl`을 넘기면 된다. 숫자가 이상하면 `docs/guides/measuring.md`부터 —
무엇이 세션에 실리는지는 종류마다 다르다(규칙·메모리는 본문 전체, 스킬·명령은 목록 한 줄, 훅은 출력, MCP는 도구 스키마).

## 판정받기

```bash
uv run scripts/judge.py            # 항목 본문을 읽고 Keep / Improve / Update / Retire / Merge 판정과 근거 → data/judgments.json
uv run scripts/decisions.py        # 판정과 쓰임을 합쳐 노드 패널 재료 → data/decisions.json
```

카드 목록은 환경마다 다르다. 동봉된 `scripts/cards.py`는 유지자 환경에서 뽑은 예시라서,
`decisions.py`를 돌리기 전에 `docs/guides/decision-cards.md`대로 자기 환경의 손잡이로 다시 쓴다.

판정 절차와 결과 읽는 법은 `docs/guides/judging.md`. 판정은 재료이지 실행이 아니다.

## 펼쳐 보기

```bash
cd ui && npm run dev               # http://127.0.0.1:5173
```

본체는 지도 한 장 — 층(시스템 프롬프트·도구·MCP·규칙·메모리·스킬·훅) 안에 단위(플러그인·서버·디렉터리·파일), 그 안에 항목.
크기는 토큰, 색은 보기 모드에 따라 쓰임·판정·조절 가능 여부. 끌 수 없는 것도 회색으로 있어서 「손댈 수 있는 것이 전체의 어디까지인가」가
보인다. 노드를 누르면 옆 패널에 재료(하는 일·구성·30일 흔적·의존·대체물·판정 근거)가 펼쳐지고, 메모와 「둔다/뺀다/줄인다」를 달 수 있다.
화면 문구는 `docs/guides/ui-terms.md`.

## 끄기 — 되돌릴 수 있는 방식만

화면은 아무것도 끄지 않는다. 메모와 선택은 `data/decisions-state.json`에 쌓이고, 실행은 에이전트(또는 사람)가
`docs/guides/disabling.md` 방식으로 한다 — 설정 토글, 심링크 해제, `.disabled/` 이동, 백업 뒤 수정 가운데 하나. 삭제는 없다.
한 일은 `data/actions.jsonl`에 적는다. 규칙·스킬 정본 디렉터리는 건드리지 않는다.

## 재사용

- 다른 사람 환경에서 돌리면 `data/`가 그 환경의 재고로 채워진다. `data/`는 개인 환경이라 커밋하지 않는다(`.gitignore`).
- 다른 하네스(Codex·Hermes)로 넓히려면 `scripts/inventory.py`의 「어디를 읽나」 목록을 그 하네스의 경로로 바꾼다.
- 지도만 필요하면 `map.py`까지, 판정까지 필요하면 `judge.py`까지. 화면 없이 `data/*.json`만 읽어도 된다.
