# korean-writing

한국어 문서·보고·README를 쓰는 에이전트에게 주는 글쓰기 규칙. 해요체 한 단락과 「한 번만 나와도 AI 티」인
금지 목록 열 줄, 합쳐 약 1,150토큰이다. 규칙은 [`SKILL.md`](SKILL.md) 한 장이 전부다.

## 왜 이만큼인가

원래 규칙(절 넷, 약 1,600토큰)을 다섯 가지로 잘라 같은 조건의 격리 실행에서 비교했다 — 규칙 없음 · 한 줄 포인터 ·
금지 목록만 · 원문 전체 · 금지 목록에 조어 금지 절과 용어집 예시를 얹은 것. sonnet 10회, opus 20회, 과제는
「밤사이 작업 로그로 쓰는 아침 보고」와 「영어 설계 메모로 쓰는 README 절」. 판정은 AI 티 탐지기와 블라인드 순위,
그리고 사람이 직접 봤다.

- **문체 한 단락 + 금지 목록**이 얻을 것을 다 얻었다. 그 위에 얹은 것들은 회차 편차 안에서 움직였다.
- **한 줄 포인터**(「쉬운 문장으로 써라」)는 규칙 없음보다 나빴다 — 볼드 라벨과 열거 예고로 서식이 늘었다.
- **용어집 예시**는 산출물 끝에 용어집 절로 복사됐다. 그래서 이 스킬에는 예시가 없다.
- **행정용어 대체어 표**(국립국어원, 150행)는 개발 문서에서 쓸 자리가 없어 효과가 없었다.
- 해요체 통일은 규칙이 있는 열여섯 편 전부에서 먹혔고, 「합니다」가 조금 섞이는 정도는 그대로 해요체로 둔다.

실험 재료와 기록은 diagram-skill-eval 저장소의 `exp/ko-writing/`와
`docs/log/2026-08-30-korean-writing-rule-experiment.md`에 있다(비공개, 요청 시).

## 쓰는 법

에이전트가 읽을 수 있는 자리에 `korean-writing/SKILL.md`를 둔다.

- **Claude Code** — 상시 규칙으로 쓰려면 `~/.claude/rules/korean-writing.md`로, 부를 때만 실으려면 `~/.claude/skills/korean-writing/`
- **Codex** — `~/.codex/skills/korean-writing/`
- **그 밖** — 프로젝트의 `AGENTS.md`에서 이 파일을 가리킨다

```bash
git clone https://github.com/choneuny/agent-kit.git
ln -s "$PWD/agent-kit/skills/korean-writing" ~/.codex/skills/korean-writing
```

한국어 문체는 매 답변에 걸리는 것이라 상시 규칙 쪽이 맞다. 스킬로 두면 글을 쓰겠다고 부를 때만 실린다.
