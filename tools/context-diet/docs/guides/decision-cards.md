# 결정 카드 지침

범위: `scripts/cards.py`가 내놓는 카드 목록, `data/decisions.json`의 계약, 그리고 카드를 자기 환경에 맞게 다시 쓰는 절차.
여는 때: 다른 환경에서 `decisions.py`를 처음 돌릴 때, 카드가 실제 손잡이와 어긋날 때, 카드에 실을 재료를 늘리거나 고칠 때.
다루지 않는 것: 판정을 내는 법(`judging.md`), 토큰을 재는 법(`measuring.md`), 화면 문구(`ui-terms.md`), 선택을 실제로 실행하는 법(`annotations.md`).
전제: 카드 하나는 결정 하나다. 손잡이가 있는 단위 — MCP 서버 하나, 플러그인 하나, 훅 등록 하나, 규칙 파일 하나, 디렉터리 하나 — 에만 카드를 만든다. 낱개 파일 수백 개는 결정이 아니라 재고다.

`cards.py`는 유지자 한 사람의 환경을 적은 예시다. `decisions.py`는 뼈대(카드 스키마, 토큰·판정·쓰임 조회, 훅 출력 읽기, 파일 쓰기)만 갖고 있고, 무엇을 카드로 세울지는 전부 `cards.py`에 있다. 남의 환경에서 그대로 돌리면 없는 MCP 서버와 없는 훅을 가리키니, 아래 절차대로 다시 쓴다.

## 카드 한 장에 무엇이 있나

위쪽은 판단 재료다. 무엇을 결정하나 한 줄, 회수하는 토큰(과 그 안의 구성), 30일 흔적(몇 번 불렸나·마지막이 언제인가·무엇이 많이 불렸나), 빼면 깨지는 것, 대체물, 판정과 근거, 합치기류면 두 본문을 나란히.

아래쪽은 사람이 손대는 자리다. 선택(둔다·뺀다·줄인다·보류), 메모, 그 카드에 달리는 짧은 대화 줄. 선택과 메모는 `data/decisions-state.json`에 쌓이고 화면이 쓴다 — `decisions.json`은 읽기 전용 재료다.

「빼면 깨지는 것」은 grep이나 설정 파일로 실제로 확인한 것만 적는다. 짐작으로 채운 의존은 결정을 잘못된 쪽으로 민다.

## 데이터 계약

`data/decisions.json` — `uv run scripts/decisions.py`가 만든다.

```
{ generated_at,
  items: [ {
    id,        // 안정 슬러그 "mcp:notion" · "rule:git-workflow" · "dir:command"
               //             "hook:SessionStart:healthcheck" · "plugin:ponytail" · "memory:MEMORY.md"
    group,     // 결정 묶음 번호 1~8 (큰 것부터. --check가 1~8이 다 있는지 본다)
    title,     // 한 줄: 무엇을 결정하나
    unit,      // 손잡이 단위 이름: "MCP 서버" "플러그인" "규칙 파일" "로컬 디렉터리" "훅 등록" …
    tokens: { reclaim,                      // 이 카드를 뺐을 때 돌아오는 토큰
              basis: "measured"|"estimated"|"mixed",
              parts: [ {name, tokens} ],    // 단위 안 구성 — 도구별·파일별
              // 훅 카드만: 어떻게 쟀는지를 함께 남긴다
              measured, method, reason, output_chars },
    usage: { calls_30d, calls_7d, last_used, top:[{name,calls}] } | null,   // 셀 수 없는 단위는 null
    breaks: [ { what,                       // 깨지는 쪽 이름
                how,                        // 사람이 읽는 한 문장 (원문 덤프 금지 — --check가 잡는다)
                evidence,                   // 그 문장의 근거가 된 원문 한 줄
                target_id } ],              // map.json 노드 id — 화면이 이름으로 짐작하지 않고 짚는다
    replacement,                            // 대체물 한 줄 또는 null
    verdicts: [ {name, verdict, merge_into, reason} ],   // 단위 안 항목들의 판정
    options: [ "keep","remove","shrink","hold" ],        // 이 카드에서 고를 수 있는 것
    pair: { a:{name,path,text,truncated}, b:{…} } | null,  // 합치기류: 두 본문을 나란히
    howto,                                  // 되돌릴 수 있는 끄기 방법 한 줄
    note                                    // 곁말 한 줄 또는 null
  } ],
  hooks_measured: { <훅 id>: {chars, tokens, measured, method, reason} },
  grep_log: [ {label, pattern, files, hits} ]   // 「깨지는 것」을 어떻게 찾았는지
}
```

`id`와 `breaks[].target_id`는 `data/map.json`의 노드 id와 같은 꼴(`<종류>:<이름>`)을 쓴다. 화면이 카드와 지도를 그 값으로 잇는다.

## 자기 환경에서 `cards.py` 다시 쓰기

에이전트가 하는 일이다. 사람의 손잡이 목록을 지어내지 말고 재고에서 끌어낸다.

1. **재료를 먼저 만든다.** `inventory.py` · `context_parse.py` · `usage.py` · `judge.py`를 돌려 `data/`에 `inventory.json` · `context-measured.json` · `usage.json` · `judgments.json`이 있게 한다. `cards.py`는 이 넷만 읽는다.

2. **큰 것부터 무리 짓는다.** `inventory.json`의 켜진 항목을 토큰 순으로 세우고, 같은 손잡이로 한 번에 껐다 켜지는 것끼리 묶는다 — 같은 MCP 서버, 같은 플러그인, 같은 디렉터리, 같은 훅 등록. 묶음 하나가 카드 하나다. 스무 장 안팎이면 충분하고, 그보다 많아지면 아직 낱개를 세고 있는 것이다.

3. **묶음을 크기 순으로 1~8번 group에 나눠 담는다.** 번호는 화면의 정렬 순서일 뿐 뜻이 정해져 있지 않다. `--check`는 1~8이 하나도 비지 않기만 본다.

4. **묶음마다 헬퍼를 고른다.** MCP 서버는 `mcp_card(서버, group, 제목, replacement=…)` — 실측 토큰과 도구별 구성, 그 서버 이름을 본문에 적은 스킬·규칙·명령·에이전트를 grep해 `breaks`까지 채운다. 디렉터리는 `dir_card(종류, [경로…], group, 제목)`. 나머지는 `card(**필드)`로 직접 짓는다. 항목 이름은 재고의 `kind`·`name`을 그대로 쓴다 — `verdicts_for`·`usage_for`·`item_tokens`가 그 쌍으로 판정·호출 수·실측 토큰을 찾는다.

5. **훅은 본문이 아니라 출력으로 잰다.** 스크립트가 읽기만 하는 것이면 `run_capture`로 돌려 그 출력을 재고, 파일을 쓰거나 자식 세션을 띄우는 것은 절대 돌리지 말고 트랜스크립트에서 읽는다. `/context`를 친 세션의 `.jsonl` 경로를 `CONTEXT_DIET_TRANSCRIPT`에 넣어 돌리면 SessionStart 훅이 실제로 주입한 본문이 `transcript_match()`로 잡힌다. 못 재는 것은 `measured: false`와 못 잰 이유를 남긴다.

6. **꺼진 것은 세지 않는다.** `settings.json`의 `enabledPlugins`가 false인 플러그인의 훅은 세션에 실리지 않는다. 예시 `cards.py`의 `measure_hooks()` 끝이 그 필터다. 재고가 낡아 꺼진 플러그인이 남아 있으면 카드가 없는 훅을 찾다 죽으니, 카드를 다시 쓰기 전에 `inventory.py`를 다시 돌린다.

7. **돌려서 확인한다.** `uv run scripts/decisions.py --check` — 중복 id, 빈 group, 원문 덤프가 된 `how`, 합칠 상대가 없는 Merge 카드를 잡고, 카드 합과 재고·실측 합을 대조해 차이를 이유와 함께 찍는다.

`cards.py`는 `decisions.py`에서 헬퍼를 가져다 쓰고, `decisions.py`는 맨 아래에서 `cards.py`를 가져온다. 순서가 그렇게 정해져 있으니 새 헬퍼가 필요하면 `decisions.py`에 두고 `cards.py`의 import 목록에 이름을 더한다.
