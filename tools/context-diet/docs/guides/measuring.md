# 재고·측정 지침

범위: `scripts/inventory.py`(재고·추정) · `scripts/context_parse.py`(`/context` 실측·보정) · `scripts/usage.py`(호출 수) ·
`scripts/installed.py`(설치 시각) · `scripts/map.py`(지도 트리)가 무엇을 어떻게 세는가, 숫자를 읽을 때 무엇을 조심하나.
여는 때: 스크립트를 돌리거나 고칠 때, 합계가 실측과 안 맞을 때, 재고에 안 잡히는 항목이 보일 때.
다루지 않는 것: 정성 판정 절차(`guides/judging.md`), 화면(코드 `ui/src/`).
전제: 세션에 「실리는 것」은 종류마다 다르다 — 규칙·메모리는 본문 전체, 스킬·명령·에이전트는 목록 한 줄(이름+설명), 훅은 출력, MCP는 도구 스키마.

## 어디를 읽나

- 규칙: `~/.claude/rules` → `~/.agents/rules` 심링크. realpath로 중복을 걷고 정본 경로를 적는다. `common/`만 세션에 실린다(이 세션 관측 기준 — 언어별 디렉터리가 언제 실리는지는 미확인).
- 메모리: cwd가 아니라 **가장 가까운 상위 프로젝트**의 `~/.claude/projects/<경로-변환>/memory/MEMORY.md`가 실린다. cwd에서 위로 올라가며 처음 맞는 것을 쓰고, 프로젝트 `CLAUDE.md`·`AGENTS.md`도 같은 층에서 같이 담는다(`/context`의 Memory files 표가 그 넷을 포함한다).
- 플러그인: `~/.claude/plugins/cache/<마켓>/<플러그인>/<버전>/` 아래 `skills/`·`commands/`·`agents/`·`.claude-plugin/plugin.json`(훅은 `hooks` 필드가 가리키는 JSON). **캐시를 훑어 세지 않는다** — superpowers가 6.2.0·6.3.0 두 판으로 남아 이중 계상된다. 설치 정본은 `installed_plugins.json`의 `installPath`, 활성 여부는 `settings.json`의 `enabledPlugins`(`<플러그인>@<마켓>`).
- 훅: `settings.json`에 등록된 것만 켜진 것. `~/.claude/hooks/`·`~/.claude/scripts/hooks/`의 나머지는 미등록 잔해다.
- MCP: `~/.claude.json`(전역·프로젝트별)과 플러그인의 `.mcp.json`. 파일에 스키마가 없으므로 토큰은 실측만. 하네스 내장 MCP(claude-in-chrome·mcp-registry·scheduled-tasks·ccd_session 등)는 어느 설정 파일에도 없다 — `/context` 실측으로만 잡힌다.
- 파일 재고에 없는 스킬 33개: Built-in 15(design·dataviz·claude-api·run 등)와 `anthropic-skills:*`·`cowork-plugin-management:*`. 실측 합 약 3.9k.

## 훅 출력

- 훅의 비용은 **출력**이다. 세션에 실제로 주입된 본문은 트랜스크립트 앞부분의
  `attachment.type == "hook_success"` 레코드에 통째로 남는다 — `content`가 비면
  `stdout`의 `hookSpecificOutput.additionalContext`가 주입된 몫이다. 실행 없이 재는 가장 싼 길이고,
  파일을 쓰는 훅(healthcheck·session-end-save)은 이 길로만 잰다.
- 실행해도 되는 것은 읽기 전용 훅뿐이다. ponytail은 플래그 파일을 쓰므로 훅 자체 대신
  `hooks/ponytail-instructions.js`의 `getPonytailInstructions(mode)`를 직접 부른다.
- **SubagentStart 훅 출력은 세션 합계 밖이다.** 서브에이전트마다 따로 주입되므로 SessionStart와
  같은 본문을 두 번 더하면 그 플러그인이 두 배로 보인다.
- `session-start-healthcheck.sh`의 평상시 출력은 배지 한 줄(15토큰)이지만, `/refresh` 스냅샷이
  대기 중이면 그 본문 전체가 같은 훅으로 들어온다. 한 세션 실측을 상시값으로 읽지 않는다.
- `session-end-save.sh`(PreCompact·SessionEnd)의 출력은 세션 컨텍스트에 안 실린다 — 트랜스크립트에
  주입 기록이 없다. 이 훅의 값은 컨텍스트가 아니라 `/learn-eval`·`/save-session` 자동 실행이다.
- 플러그인 훅은 `plugin.json`의 `hooks` 필드만이 아니라 `hooks/hooks.json`으로도 걸린다 —
  superpowers가 그 꼴이라 재고에 안 잡힌 채 세션마다 1.4k를 붓는다.

## 토큰 추정과 보정

- 추정식은 `ascii_bytes / a + non_ascii_chars * b`. 계수는 `data/calibration.json`이 있으면 그것을, 없으면 기본값(a=4.0, b=1.5).
- 보정은 API 키 없이 `/context` 실측으로 한다. `context_parse.py`가 행별 실측이 정확한 메모리 파일과 에이전트(59개)로 두 계수를 최소제곱으로 맞춘다. 스킬 행은 `~`·`< 20` 근사라 보정 표본에서 뺀다.
- 검산은 「규칙 + 메모리 = `/context`의 Memory files」다(08-22: 25.4k + 9.0k ≈ 34.5k). 안 맞으면 계수보다 **집합 차이**(재고에 없는 항목, 이중 계상)부터 의심한다.
- 스킬 목록은 계수 하나로 못 맞춘다 — 짧은 에이전트 줄과 긴 스킬 설명의 바이트/토큰 비가 달라 매칭 124개 기준 48% 과대다. 스킬 수치는 상한으로 읽는다(길이별 계수 분리는 미결).
- 실측 표본과 파일의 시점이 어긋나면 보정이 흔들린다(실측 뒤 파일이 자라면 계수가 움직인다). 표본은 재고 직후에 뜬다.
- `/context` 출력은 트랜스크립트 jsonl에 `local_command` 레코드로 남는다 — `context_parse.py --from-transcript <jsonl>`로 수확한다. 붙여넣기로 옮겨 적지 않는다(한 번 옮겨 적다 값 하나를 틀렸다).
- 세션에 따라 `/context`가 행 표 없는 **압축 표시**(범주 합계 + 개수만)로 나온다(2026-08-24 Opus 세션 실측). 그 표본은 수확이 안 되니 개수·합계 검산으로만 쓰고, 상세 표가 나오는 세션에서 다시 뜬다.

## 호출 수

- 트랜스크립트는 두 자리에 있다. 세션 제 파일 `~/.claude/projects/*/*.jsonl`(634개)과 **서브에이전트마다 한 개씩인
  `~/.claude/projects/*/<세션-uuid>/subagents/agent-*.jsonl`(1,226개 866MB)**. `*/*.jsonl` 글롭은 뒤엣것을 통째로 놓친다 —
  서브가 부른 스킬·에이전트·MCP가 전부 0으로 잡혔다. 두 글롭을 합쳐 읽는다(1,840개 16초).
- **`isSidechain`은 이 하네스에서 언제나 false다**(전수 확인: true 0건, false 235,191건). 서브에이전트 판별은 이 필드가 아니라
  파일이 `subagents/` 아래 있는가로 한다. 서브 메타(`agent-*.meta.json`)에 `agentType`·`parentAgentId`·`model`이 있다.
- 호출자 구분(`by_30d`)은 셋이다. 서브에이전트 파일이면 subagent · 훅이 띄운 헤드리스 세션이면 hook · 나머지는 human.
  훅 세션은 첫 열 줄에 `session-end-save.sh`가 넣는 프롬프트 문구(`Automated hook — no user confirmation` 또는
  `and run /save-session`)로 알아본다. `/learn-eval` 179회·`/save-session` 99회가 전부 그 세션에서 나온다 — 사람이 부른 적이 없다.
- 트랜스크립트를 줄 단위로 읽는다(634개 0.70GB에 1.4초). mtime은 전부 최근이라 걸러 주지 않는다 — 타임스탬프로만 자른다.
- 세는 것: Skill 도구의 `skill`, 사용자 입력의 `/name`, Agent 도구의 `subagent_type`, `mcp__<서버>__<도구>`. 내장 슬래시 명령(`/clear`·`/model` 등)은 뺀다. 서브에이전트 트랜스크립트도 포함한다(서브가 부른 것도 컨텍스트를 먹었다).
- 도구 인자 JSON은 콜론 뒤 공백이 없다(`"skill":"docs-upkeep"`). `json.dumps` 출력을 grep 패턴으로 쓰면 0이 나온다.
- 플러그인 MCP 도구는 `mcp__plugin_<플러그인>_<서버>__<도구>`라 재고의 `<플러그인>:<서버>` 이름과 맞추려면 변환이 필요하다(미결).
- `skill-stocktake/scripts/scan.sh`의 호출 수는 이 기계에 없는 `~/.claude/observations.jsonl`을 읽는다 — 대조 상대가 못 된다. `usage.py --check`는 grep으로 세 항목을 독립 재집계해 맞춘다.

## 셸 함정

- `~/.claude/skills`는 `~/.agents/skills`로 가는 스킬별 심링크다. grep 대상을 모을 때 realpath로
  걷지 않으면 같은 파일이 두 번 잡힌다.
- 이 세션 셸에서 `node -e`는 권한에 막힌다 — 임시 `.js` 파일로 써서 `node <파일>`로 돌린다.
- 이 세션 셸의 `grep`은 함수로 덮여 있어 `-m`·`-oF`가 죽는다. 트랜스크립트 훑기는 파이썬이나 `bash -c`.
- 헤드리스 크롬은 `libnss3`·`libnspr4`가 시스템에 없어 그냥은 안 뜨지만 sudo 없이 된다 — `apt-get download --print-uris`로 .deb 주소를 받아 curl로 받고 `dpkg-deb -x`로 스크래치패드에 푼 뒤 `LD_LIBRARY_PATH=<그곳>/usr/lib/x86_64-linux-gnu`로 띄운다(2026-08-23 실측).
- Vite SSR 산출물은 패키지 안(`--outDir dist-ssr`)에 뽑아야 돌아가고, `render()`는 동기라 fetch로 채우는 표는 안 나온다. 행 수 검증은 `ui/check.mjs`(합치기 함수를 node로 직접 호출).

## 설치 시각

`installed.py`가 출처 넷을 우선순위대로 밟고 `confidence`에 어느 출처였는지 적는다. 못 구하면 `null` — 없는 척하지 않는다.

- `plugin-meta` — `~/.claude/plugins/installed_plugins.json`의 `installedAt`. 플러그인이 준 항목(스킬·훅·MCP)이 전부 여기서 온다.
- `agents-git` — `git -C ~/.agents log --diff-filter=A --reverse --format=@%aI --name-only` 한 번으로 전 파일의 첫 커밋을 모은다.
  파일마다 `git log`를 돌리면 121번을 돈다.
- `birth-time` — `stat -c %W`. ext4가 이 기계에서 birth time을 기록한다(실측). **파이썬에는 리눅스용 `st_birthtime`이 없다** —
  `os.stat()`에 그 필드가 아예 안 붙으므로 셸의 `stat`을 쓴다.
- `transcript-first` — 트랜스크립트에 `mcp__<서버>__`가 처음 나온 날. MCP 서버는 파일이 없어 이 길뿐이다.

읽을 때 조심할 것:
- **바닥이 두 개 있다.** `~/.agents`는 2026-08-14에 정본으로 세워졌고 `~/.claude` 파일 다수의 birth time은 2026-07-03(devbox 이사로
  복사된 날)이다. 그보다 이른 날짜는 나올 수 없다 — 그 날짜는 「이 기계에 온 날」이지 「만든 날」이 아니다.
- **MCP 서버에 birth time을 쓰지 마라.** 서버의 `path`는 공용 `~/.claude.json`이라 그 파일을 마지막으로 고쳐 쓴 날이 나온다
  (실제로 전부 오늘로 찍혔다). 서버는 트랜스크립트 첫 등장으로만 잰다.
- 트랜스크립트 첫 등장은 **처음 쓴 날**이지 설치한 날이 아니다. 설치해 두고 안 쓰다 나중에 처음 부르면 늦게 잡힌다.

## 지도 (`map.py` → `data/map.json`)

- 층은 `/context` 범주를 그대로 따르고, 층 합계를 그 범주 값과 `--check`로 대조한다. 08-22 대조 차: MCP -201 · 메모리 -50 ·
  스킬 +310 · 에이전트 +12 — 전부 `/context`가 100 단위로 반올림해 적는 몫이다.
- **`/context` 헤더의 총합과 범주 표의 합은 다르다.** 헤더는 117.2k인데 지연 로드를 뺀 범주 합은 120.5k다. 계산 오류를 찾지 말 것 —
  표기 반올림이다. 지연 로드(MCP 58.5k · 시스템 도구 17k)는 헤더 총합 밖이다(퍼센트를 더하면 정확히 100%가 된다).
- 훅 출력은 `/context` 범주에 없다 — 주입은 Messages로 들어간다. 지도에는 층으로 두되 설정 부분 대조에서는 뺀다.
- 노드 id는 `<kind>:<name>`(`skill:debate`·`mcp:notion`·`rule:docs-and-memory`)이라 judgments·summaries·installed와 그대로 조인된다.
  `unit_id`는 그 항목이 걸린 `decisions.json` 카드 id다.
- MCP 도구 하나하나는 지도 노드가 아니다 — 카드의 `parts`에 이미 있다. MCP 도구가 **결과로 돌려주는 본문 크기**는 안 쟀다
  (주 축은 상주 토큰이고, 결과 크기는 낭비가 아니라 일이다).
- 이상치 `flags:["body_outlier"]`는 목록 한 줄 대비 본문이 20배를 넘거나 본문이 3k를 넘는 항목이다(120개, 최대
  `superpowers:subagent-driven-development` 13.2k).

## 언어 바꾸기는 답이 아니다 (2026-08-23 실측)

한국어 규칙·메모리를 영어로 옮겨도 상주 토큰은 1~4%(메모리 층 34.5k 중 1.2k~5.2k)만 준다. 한국어는 글자당 토큰이 영어의 약 2.45배(0.944 대 0.384 tok/글자, `/context` 행 실측 역산)지만 뜻을 지킨 영어 번역은 글자가 2.1~2.4배로 불어 상쇄된다. 줄이려면 언어가 아니라 내용(중복·군더더기)을 줄인다.
- 영어 산문 실측 비율은 2.61바이트/토큰(중앙, 0.325~0.397 tok/글자)으로 보정 계수 `ascii_div 2.445`보다 6% 낮다 — 영어 비중 큰 항목의 파일 추정은 그만큼 과대다.

## 규칙이 실제로 실리는지 확인하는 법

규칙은 시스템 프롬프트로 들어가 세션 jsonl에 남지 않는다(2026-08-24 전수 스캔). 확인은 새 `claude -p` 세션에 「지금 컨텍스트에 첨부된 규칙 파일 경로를 한 줄씩 나열하라」고 시켜 목록을 받는다 — 모델 출력이라 한 단계 약한 증거다. `paths:` 규칙과 훅 주입은 트랜스크립트에 남는다(`nested_memory` 첨부·system reminder)로 센다.

## 파일 읽기·쓰기는 대부분 Bash로 간다 (2026-08-24 실측, 30일)

tool_use 86,510건 가운데 Bash 55,990 · Read 9,784 · Edit 8,771 · Write 3,338. 파일 읽기의 76%가 Bash(`cat`·`head`·`sed -n`·`grep`), 쓰기의 51%가 Bash(`sed -i`·heredoc·`cat >`·`echo >`). MultiEdit·NotebookEdit는 0건. 그래서 Read·Edit·Write 도구에만 거는 장치(내장 `paths:` 게이트, 도구 매처 훅)는 파일 작업의 3분의 1만 본다 — 규칙 훅은 Bash 명령에서 경로를 뽑아야 한다. 셈은 줄 단위 스캔 + Bash는 정규식 분류(휴리스틱), grep 독립 재집계와 Read·Edit 완전 일치.
- 명령·에이전트를 끌 때 `~/.claude/commands/.disabled/`처럼 **안쪽 숨김 디렉터리는 발견을 못 막는다**(`.disabled:이름`으로 실림, 2026-08-24 실측). `~/.claude/commands-disabled/`·`agents-disabled/`처럼 밖으로 옮긴다. `inventory.py`는 그 두 경로를 아직 안 훑는다.
