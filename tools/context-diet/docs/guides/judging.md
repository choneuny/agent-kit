# 정성 판정 지침

범위: `scripts/judge.py`로 항목을 묶어 서브에이전트에 판정시키고 `data/judgments.json`으로 모으는 절차.
여는 때: 재고가 바뀌어 판정을 다시 돌릴 때, 판정 품질이 의심될 때.
다루지 않는 것: 끄기 실행(`guides/disabling.md`).
전제: 판정은 비용(토큰)·호출 수가 아니라 **본문을 읽은 근거**로 낸다. 비용과 호출 수는 재료다.

## 절차

1. `uv run scripts/inventory.py` 뒤 `uv run scripts/judge.py prepare` — 켜진 항목 + 실측 전용 항목을 kind별 균등 묶음(11~14개)으로 `data/judgments/batch-*.input.json`에 쓴다. `judgments.json`에 같은 mtime 판정이 있으면 뺀다.
2. 묶음마다 서브에이전트(opus)를 띄운다 — 한 번에 다섯 이하. **서브가 도는 동안 `prepare`를
   재실행하지 마라** — 입력 묶음이 재배열돼 서브가 읽은 파일과 어긋난다(2026-08-24 실측:
   돌던 서브의 10번째 항목이 도중에 교체됐다). 판정 대상을 늘리려면 도는 묶음이 다 돌아온 뒤에. 프롬프트에는 **공용 지침 `data/judgments/PROMPT.md`의 경로**와 묶음 파일 경로, 묶음별 특이사항 몇 줄만. 지침 본문을 프롬프트마다 복사하면 부모 컨텍스트가 3만 토큰 넘게 샌다. 이름 목록(`all-names.md`)도 파일로 넘긴다.
3. 서브는 항목 본문을 직접 읽고(파일이 없는 내장 항목은 실측 토큰과 세션에 붙은 설명으로) `batch-*.json`에 쓴다. 돌아온 묶음마다 reason 2~3개를 본문과 대조한다.
4. `uv run scripts/judge.py merge && uv run scripts/judge.py --check` — 대상 수 일치·어휘·Merge 대상 실재·중복을 본다.

## 읽을 때

- 하네스 내장 41항목(내장 MCP 서버·Built-in 스킬)은 본문이 없어 confidence가 medium에 몰리고 끄는 손잡이도 없다. 고정 비용으로 본다.
- 플러그인 소속 스킬의 Retire·Merge는 플러그인을 통째로 끌지의 재료다. 개별로는 못 끈다.
- 규칙·메모리·MCP는 호출 수가 없다 — 본문과 대상 실재(파일·프로젝트가 있나)로만 낸 판정이다.
- 「대상 코드가 없다」류 근거는 `find -maxdepth 4~5` 범위 실측이다. 더 깊거나 Windows 쪽은 안 봤다.
