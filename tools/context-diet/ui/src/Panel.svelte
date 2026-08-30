<script>
  import { fmtTokens, fmtAgo, fmtDate, INSTALL_SOURCE, COUNTABLE, choiceLabel } from './lib.js'

  let { node, card, entry, saving, borrowed = null, onchoose, onmemo, onsay, onclose, onhover, onzoom, onjump } = $props()

  let memo = $state('')
  let said = $state('')
  let lastId = null

  // 노드가 바뀌면 칸을 그 노드의 것으로 갈아 끼운다
  $effect(() => {
    if (node?.id !== lastId) {
      lastId = node?.id
      memo = entry?.memo ?? ''
      said = ''
    }
  })

  const options = $derived(card?.options?.length ? card.options : ['keep', 'remove', 'shrink', 'hold'])
  const kids = $derived((node?.children ?? []).slice().sort((a, b) => b.tokens - a.tokens))
  const verdicts = $derived(
    (card?.verdicts ?? []).filter((v) => v.name === node?.name)
  )

  const CONFIDENCE = { high: '근거 뚜렷', medium: '근거 보통', low: '근거 약함' }

  const CALLER = { hook: '훅이 부른다', mcp: '사람·서브가 부른다', mcp_tool: '사람·서브가 부른다',
    skill: '사람·서브가 부른다', command: '사람이 부른다', agent: '서브로 뜬다' }

  let timer
  function typed() {
    clearTimeout(timer)
    timer = setTimeout(() => onmemo?.(memo), 800)
  }
  function send() {
    if (!said.trim()) return
    onsay?.(said.trim())
    said = ''
  }
</script>

<aside class="panel">
  <header>
    <div>
      <p class="kind">{node.kind ?? '항목'}</p>
      <h2>{node.name}</h2>
    </div>
    <div class="acts">
      {#if node.children?.length}
        <button class="into" onclick={() => onzoom?.(node)}>안으로</button>
      {/if}
      <button class="x" onclick={onclose} aria-label="패널 닫기">✕</button>
    </div>
  </header>

  <div class="body">
    {#if node.summary || node.note}
      <p class="lead">{node.summary ?? node.note}</p>
    {/if}

    <dl class="facts">
      <dt>토큰</dt>
      <dd class="num">
        {fmtTokens(node.tokens)}
        <span class="weak">{node.basis === 'measured' ? '측정값' : node.basis === 'estimated' ? '추정값' : '출처 없음'}</span>
      </dd>
      {#if node.body_tokens != null && node.body_tokens !== node.tokens}
        <dt>본문</dt><dd class="num">{fmtTokens(node.body_tokens)}</dd>
      {/if}
      {#if node.deferred}
        <dt>실리는 때</dt><dd>부르면 그때 — 평소엔 이름 한 줄</dd>
      {/if}
      <dt>설치</dt>
      <dd>
        {fmtAgo(node.installed_at) ?? '모름'}
        {#if node.installed_source}
          <span class="weak">{INSTALL_SOURCE[node.installed_source] ?? node.installed_source}{CONFIDENCE[node.installed_confidence] ? ` · ${CONFIDENCE[node.installed_confidence]}` : ''}</span>
        {/if}
      </dd>
      <dt>30일</dt>
      <dd>
        {#if node.usage?.calls_30d != null}
          <span class="num">{node.usage.calls_30d}회</span>
          {#if node.usage.calls_7d != null}<span class="num"> · 7일 {node.usage.calls_7d}회</span>{/if}
          <span class="weak">
            {CALLER[node.kind] ?? '기록 기준'}{node.usage_from ? ` · ${node.usage_from} 기준` : ''}
            {node.usage.last_used ? ` · 마지막 ${fmtDate(node.usage.last_used)}` : ''}
          </span>
        {:else if COUNTABLE.has(node.kind)}
          부른 기록 없음
        {:else}
          호출로 세지 않는다 — 늘 실린다
        {/if}
      </dd>
      {#if node.flags?.length}
        <dt>표시</dt><dd class="warn">{node.flags.join(' · ')}</dd>
      {/if}
    </dl>

    {#if kids.length}
      <section>
        <h3>구성 <span class="n num">{kids.length}개</span></h3>
        <ul class="bars">
          {#each kids.slice(0, 12) as k}
            <li>
              <span class="bar-name">{k.name}</span>
              <span class="bar"><span style="width:{(k.tokens / kids[0].tokens) * 100}%"></span></span>
              <span class="bar-num num">{fmtTokens(k.tokens)}</span>
            </li>
          {/each}
        </ul>
        {#if kids.length > 12}<p class="more">아래로 {kids.length - 12}개 더 — 타일을 눌러 들어가라</p>{/if}
      </section>
    {/if}

    {#if borrowed && (card?.breaks?.length || card?.replacement || card?.howto || card?.pair)}
      <p class="borrowed">아래 재료는 단위 「{borrowed}」 기준이다 — 이 항목 하나만의 것이 아니다.</p>
    {/if}

    {#if card?.breaks?.length}
      <section>
        <h3>빼면 깨지는 것 <span class="n num">{card.breaks.length}</span></h3>
        <ul class="breaks">
          {#each card.breaks as b}
            <li
              onmouseenter={() => onhover?.(b)}
              onmouseleave={() => onhover?.(null)}
            >
              <button class="b-what" onclick={() => onjump?.(b)}>{b.what}</button>
              <p class="b-how">{b.how}</p>
              {#if b.evidence}
                <details class="evi">
                  <summary>원문</summary>
                  <p>{b.evidence}</p>
                </details>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if card?.replacement}
      <section>
        <h3>대체물</h3>
        <p>{card.replacement}</p>
      </section>
    {/if}

    {#if node.verdict || verdicts.length}
      <section>
        <h3>판정과 근거</h3>
        <p class="verdict">
          <span class="v v-{(node.verdict ?? verdicts[0]?.verdict ?? '').toLowerCase()}">
            {node.verdict ?? verdicts[0]?.verdict}
          </span>
          {#if node.merge_into}<span class="weak">→ {node.merge_into}</span>{/if}
        </p>
        <p class="reason">{node.reason ?? verdicts[0]?.reason}</p>
      </section>
    {/if}

    {#if card?.pair}
      <section>
        <h3>합칠 두 본문</h3>
        <div class="pair">
          {#each [card.pair.a, card.pair.b] as side}
            <div>
              <p class="p-name">{side.name}</p>
              <p class="p-path">{side.path}</p>
              <pre>{side.text}</pre>
            </div>
          {/each}
        </div>
      </section>
    {/if}

    {#if card?.howto}
      <section>
        <h3>빼는 법</h3>
        <p class="howto">{card.howto}</p>
      </section>
    {/if}
  </div>

  <div class="note">
    <p class="lab">선택</p>
    <div class="choices" role="group" aria-label="선택">
      {#each options as o}
        <button
          class:on={entry?.choice === o}
          disabled={node.fixed}
          onclick={() => onchoose?.(entry?.choice === o ? null : o)}
        >{choiceLabel(o)}</button>
      {/each}
    </div>
    {#if node.fixed}
      <p class="why">고정 — 하네스가 싣는 것이라 여기서 끄지 못한다.</p>
    {/if}

    <label class="memo">
      <span class="lab">메모</span>
      <textarea rows="3" bind:value={memo} oninput={typed} placeholder="여기서 무엇이 마음에 걸리나"></textarea>
    </label>
    <p class="save" class:bad={saving === 'fail'}>
      {saving === 'saving' ? '저장 중' : saving === 'fail' ? '저장 실패 — 다시 써 보라' : entry?.updated_at ? `저장됨 ${entry.updated_at.slice(11, 16)}` : ''}
    </p>

    {#if entry?.thread?.length}
      <ul class="thread">
        {#each entry.thread as t}
          <li class:agent={t.by === 'agent'}>
            <span class="who">{t.by === 'agent' ? '에이전트' : '나'}</span>
            <span>{t.text}</span>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="say">
      <input bind:value={said} placeholder="물어볼 것" onkeydown={(e) => e.key === 'Enter' && send()} />
      <button onclick={send} disabled={!said.trim()}>보내기</button>
    </div>
  </div>
</aside>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    width: 380px;
    flex: none;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r);
    overflow: hidden;
  }
  @media (min-width: 1700px) { .panel { width: 440px; } }

  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4);
    border-bottom: 1px solid var(--line);
  }
  .kind { margin: 0; font-size: 12.5px; color: var(--muted); }
  h2 { margin: 0; font-size: 16px; font-weight: 600; line-height: 1.35; overflow-wrap: anywhere; }
  .acts { display: flex; align-items: center; gap: var(--sp-1); flex: none; }
  .into {
    padding: 3px var(--sp-2);
    font-size: 12.5px;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    cursor: pointer;
  }
  .into:hover { background: var(--surface-2); }
  .x { padding: 2px 6px; background: none; border: 0; color: var(--muted); cursor: pointer; border-radius: 2px; }
  .x:hover { background: var(--surface-2); color: var(--text); }

  .body { flex: 1; overflow-y: auto; padding: var(--sp-4); }
  .lead { margin: 0 0 var(--sp-3); font-size: 14px; line-height: 1.6; }

  .facts { display: grid; grid-template-columns: 54px 1fr; gap: var(--sp-1) var(--sp-3); margin: 0; font-size: 12.5px; }
  .facts dt { color: var(--muted); }
  .facts dd { margin: 0; }
  .weak { display: block; color: var(--muted); }
  .warn { color: var(--hold); }

  section { margin-top: var(--sp-6); }
  h3 { margin: 0 0 var(--sp-2); font-size: 12.5px; font-weight: 600; color: var(--muted); }
  h3 .n { color: var(--line-strong); margin-left: var(--sp-1); }
  section p { margin: 0; font-size: 12.5px; line-height: 1.6; }

  .bars { margin: 0; padding: 0; list-style: none; }
  .bars li { display: grid; grid-template-columns: 1fr 64px 44px; align-items: center; gap: var(--sp-2); padding: 2px 0; font-size: 12.5px; }
  .bar-name { overflow-wrap: anywhere; }
  .bar { height: 5px; background: var(--surface-2); border-radius: 1px; }
  .bar span { display: block; height: 100%; background: var(--accent); opacity: 0.55; border-radius: 1px; }
  .bar-num { text-align: right; color: var(--muted); }
  .more { margin-top: var(--sp-2); color: var(--muted); }

  .breaks { margin: 0; padding: 0; list-style: none; }
  .breaks li { padding: var(--sp-2); border-left: 2px solid var(--line); }
  .breaks li:hover { background: var(--surface-2); border-left-color: var(--hold); }
  .b-what {
    padding: 0;
    background: none;
    border: 0;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--accent);
    text-align: left;
    cursor: pointer;
  }
  .b-what:hover { text-decoration: underline; }
  .b-how { color: var(--muted); overflow-wrap: anywhere; }
  .evi summary { font-size: 12.5px; color: var(--accent); cursor: pointer; }
  .evi p { margin-top: var(--sp-1); padding-left: var(--sp-2); border-left: 2px solid var(--line); color: var(--muted); overflow-wrap: anywhere; }
  .borrowed {
    margin: var(--sp-6) 0 0;
    padding: var(--sp-2);
    background: var(--surface-2);
    border-radius: 2px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .verdict { display: flex; align-items: baseline; gap: var(--sp-2); margin-bottom: var(--sp-2); }
  .v { font-size: 14px; font-weight: 600; }
  .v-keep { color: var(--live); }
  .v-improve { color: var(--accent); }
  .v-update { color: var(--hold); }
  .v-retire { color: var(--idle); }
  .v-merge { color: var(--merge); }
  .reason { color: var(--text); }

  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
  .p-name { font-weight: 600; }
  .p-path { color: var(--muted); overflow-wrap: anywhere; margin-bottom: var(--sp-1); }
  .pair pre {
    max-height: 260px;
    margin: 0;
    padding: var(--sp-2);
    overflow: auto;
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: 2px;
    font-size: 12.5px;
    line-height: 1.5;
    white-space: pre-wrap;
    font-family: var(--font);
  }

  .howto { padding: var(--sp-2); background: var(--surface-2); border-radius: 2px; overflow-wrap: anywhere; }

  .note > .lab { margin: 0 0 var(--sp-2); }
  .note { flex: none; padding: var(--sp-3) var(--sp-4) var(--sp-4); border-top: 1px solid var(--line); background: var(--surface-2); }
  .choices { display: flex; flex-wrap: wrap; gap: var(--sp-1); }
  .choices button {
    padding: 5px var(--sp-3);
    font-size: 12.5px;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    cursor: pointer;
  }
  .choices button:hover:not(:disabled) { background: var(--bg); }
  .choices button.on { background: var(--accent); border-color: var(--accent); color: var(--surface); }
  .choices button:disabled { opacity: 0.45; cursor: not-allowed; }
  .why { margin: var(--sp-2) 0 0; font-size: 12.5px; color: var(--muted); }

  .memo { display: block; margin-top: var(--sp-3); }
  .lab { display: block; font-size: 12.5px; color: var(--muted); margin-bottom: var(--sp-1); }
  textarea, .say input {
    width: 100%;
    padding: 6px var(--sp-2);
    font: inherit;
    font-size: 12.5px;
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    resize: vertical;
  }
  .save { min-height: 18px; margin: var(--sp-1) 0 0; font-size: 12.5px; color: var(--muted); }
  .save.bad { color: var(--idle); }

  .thread { margin: var(--sp-2) 0 0; padding: 0; list-style: none; font-size: 12.5px; }
  .thread li { padding: var(--sp-1) 0; }
  .thread .who { color: var(--muted); margin-right: var(--sp-2); }
  .thread li.agent { color: var(--accent); }

  .say { display: flex; gap: var(--sp-1); margin-top: var(--sp-2); }
  .say button {
    flex: none;
    padding: 6px var(--sp-3);
    font-size: 12.5px;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    cursor: pointer;
  }
  .say button:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
