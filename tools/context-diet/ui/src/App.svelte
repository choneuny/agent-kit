<script>
  import Treemap from './Treemap.svelte'
  import Panel from './Panel.svelte'
  import { MODES, LEGENDS, fmtTokens, fmtDate, spine, totals, pathTo, stateOf, metaBits,
    inheritUsage, cardFor, nodeIndex, breakTarget, counts, choiceLabel,
    deferredTokens, residentOnly } from './lib.js'

  let state = $state('loading') // loading | ready | empty | error
  let error = $state('')
  let map = $state(null)
  let mode = $state('control')
  let focusId = $state(null)
  let selected = $state(null)      // 고른 노드의 id
  let cards = $state(new Map())    // 결정 카드 (decisions.json)
  let notes = $state({})           // 주석 (decisions-state.json)
  let saving = $state('idle')      // idle | saving | fail
  let hoverBreak = $state(null)
  let showActions = $state(false)
  let withLazy = $state(true)      // 지연 로드까지 지도에 놓는다

  // 세션 시작에 실리는 것과 부를 때 실리는 것을 가른다
  const full = $derived(map?.root ?? null)
  const resident = $derived(full ? residentOnly(full) : null)
  const lazyTokens = $derived(full ? deferredTokens(full) : 0)
  const root = $derived((withLazy ? full : resident) ?? null)
  const trail = $derived(root ? (pathTo(root, focusId ?? root.id) ?? [root]) : [])
  const focus = $derived(trail[trail.length - 1] ?? null)
  const sums = $derived(root ? totals(root) : null)
  const bars = $derived(root ? spine(root) : [])
  const layerId = $derived(trail.length > 1 ? trail[1].id : null)
  const index = $derived(root ? nodeIndex(root) : null)
  const selNode = $derived(selected && root ? (pathTo(root, selected)?.at(-1) ?? null) : null)
  const selCard = $derived(selNode ? cardFor(selNode, cards) : null)
  // 낱 항목이 단위 카드를 빌려 썼으면 어느 단위 것인지 밝힌다
  const borrowed = $derived.by(() => {
    if (!selNode || !selCard || selCard.id === selNode.id) return null
    const up = pathTo(root, selNode.id) ?? []
    return up.findLast?.((n) => n.kind === 'unit')?.name ?? selCard.unit ?? null
  })
  const tally = $derived(counts(notes))
  // 실측 표본을 뜬 뒤에 하네스를 건드렸나 (data/actions.jsonl 마지막 실행 시각)
  const stale = $derived(
    !!map?.source?.stale_since && !!map?.source?.measured_at &&
    map.source.stale_since.slice(0, 10) > map.source.measured_at)

  // 주석이 달린 노드 표시
  const marks = $derived(new Map(Object.entries(notes)
    .filter(([, v]) => v && (v.choice || v.memo?.trim() || v.thread?.length))
    .map(([id, v]) => [id, {
      choice: v.choice,
      title: [choiceLabel(v.choice), v.memo?.trim() ? '메모 있음' : null].filter(Boolean).join(' · '),
    }])))

  // 빼면 깨지는 것 → 지도에서 밝힐 노드들
  const spot = $derived.by(() => {
    if (hoverBreak) {
      const t = breakTarget(hoverBreak, index)
      return t ? new Set([t.id]) : null
    }
    if (!selCard?.breaks?.length) return null
    const ids = selCard.breaks.map((b) => breakTarget(b, index)?.id).filter(Boolean)
    return ids.length ? new Set(ids) : null
  })

  // 실행 목록: 고른 것 + 빼는 법
  const actions = $derived(Object.entries(notes)
    .filter(([, v]) => v?.choice && v.choice !== 'hold')
    .map(([id, v]) => {
      const node = root ? pathTo(root, id)?.at(-1) : null
      return { id, choice: v.choice, memo: v.memo, node, card: node ? cardFor(node, cards) : null }
    })
    .filter((a) => a.node))

  async function load() {
    state = 'loading'
    try {
      const res = await fetch('/data/map.json')
      if (!res.ok) throw new Error(`지도를 읽지 못했다 (HTTP ${res.status})`)
      const doc = await res.json()
      if (!doc?.root?.children?.length) { map = null; state = 'empty'; return }
      inheritUsage(doc.root)
      map = doc
      state = 'ready'
      // 카드와 주석은 없어도 지도는 뜬다
      cards = new Map((await get('/data/decisions.json'))?.items?.map((c) => [c.id, c]) ?? [])
      notes = (await get('/data/decisions-state.json')) ?? {}
    } catch (e) {
      error = e.message || String(e)
      state = 'error'
    }
  }
  load()

  async function get(url) {
    try {
      const r = await fetch(url)
      if (!r.ok) return null
      return await r.json()
    } catch { return null }
  }

  /** 에이전트가 파일에 단 답을 늦게라도 보이게 한다. */
  async function refresh() {
    if (state !== 'ready' || saving === 'saving') return
    const fresh = await get('/data/decisions-state.json')
    if (fresh) notes = fresh
  }

  let lastSel = null
  $effect(() => {
    if (selected && selected !== lastSel) { lastSel = selected; refresh() }
    if (!selected) lastSel = null
  })

  /** 주석 저장 — 선택은 곧바로, 메모는 패널이 800ms 기다렸다 부른다. */
  async function save(patch) {
    if (!selNode) return
    saving = 'saving'
    const prev = notes[selNode.id] ?? { choice: null, memo: '', thread: [] }
    try {
      const r = await fetch('/api/decision', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ id: selNode.id, ...patch }),
      })
      if (!r.ok) throw new Error(String(r.status))
      const { updated_at } = await r.json()
      const thread = patch.message
        ? [...(prev.thread ?? []), { by: 'user', at: updated_at, text: patch.message }]
        : (prev.thread ?? [])
      notes = { ...notes, [selNode.id]: { ...prev, ...patch, message: undefined, thread, updated_at } }
      saving = 'idle'
    } catch {
      saving = 'fail'
    }
  }

  function zoom(node) { focusId = node.id; selected = node.id }
  function pick(node) { selected = node.id }

  /** 「빼면 깨지는 것」을 눌렀을 때 그 상대에게 간다 — 부모까지 열고 고른다. */
  function jump(b) {
    const target = breakTarget(b, index)
    if (!target || !root) return
    const path = pathTo(root, target.id)
    focusId = path?.at(-2)?.id ?? root.id
    selected = target.id
    hoverBreak = null
  }
  function up() {
    if (trail.length > 1) focusId = trail[trail.length - 2].id
  }
  function key(e) {
    if (e.key !== 'Escape') return
    if (showActions) showActions = false
    else if (selected) selected = null
    else up()
  }
</script>

<svelte:window onkeydown={key} onfocus={refresh} />

<main>
  <header>
    <div class="bar">
      <div>
        <h1>컨텍스트 지도</h1>
        <p class="sub">세션마다 실리는 것을 넓이로 놓았다. 넓이는 토큰이다.</p>
      </div>
      <div class="tools">
        {#if state === 'ready'}
          <p class="tally num">
            주석 {tally.memo} · 뺀다 {tally.remove} · 줄인다 {tally.shrink}
          </p>
          <button class="acts" class:on={showActions} onclick={() => (showActions = !showActions)}>
            실행 목록
          </button>
        {/if}
      <div class="modes" role="group" aria-label="지연 로드">
        <button class:on={withLazy} onclick={() => (withLazy = true)} aria-pressed={withLazy}>지연 포함</button>
        <button class:on={!withLazy} onclick={() => (withLazy = false)} aria-pressed={!withLazy}>상주만</button>
      </div>
      <div class="modes" role="group" aria-label="색 모드">
        {#each MODES as [id, label]}
          <button class:on={mode === id} onclick={() => (mode = id)} aria-pressed={mode === id}>
            {label}
          </button>
        {/each}
      </div>
      </div>
    </div>

    {#if state === 'ready'}
      <div class="totals">
        <span class="big num">{fmtTokens(sums.total)}</span>
        <span class="unit">토큰 · {withLazy ? '지연까지 합쳐' : '세션 시작에 실림'}</span>
        <span class="split">
          <span class="dot s-fixed"></span>고정 <b class="num">{fmtTokens(sums.fixed)}</b>
          <span class="dot s-open"></span>조절 가능 <b class="num">{fmtTokens(sums.open)}</b>
        </span>
        <span class="lazy">
          {withLazy ? '그중 부르면 실림(지연)' : '부르면 실림(지연)'} <b class="num">{fmtTokens(lazyTokens)}</b>
          {#if !withLazy}<span class="off">지도에서 뺌</span>{/if}
        </span>
        {#if map.source?.measured_at}
          <span class="when">{fmtDate(map.source.measured_at)} 잰 값</span>
        {:else if map.generated_at}
          <span class="when">{fmtDate(map.generated_at)} 잰 값</span>
        {/if}
        {#if stale}
          <span class="stale" title="지도는 그 뒤 바뀐 것을 빼고 그렸지만, 남은 항목의 토큰은 표본을 뜬 날의 값이다">
            실측 이후 바뀐 것 있음 — 새 /context 표본 필요
          </span>
        {/if}
      </div>

      <div class="spine" role="group" aria-label="층">
        {#each bars as b}
          <button
            class="seg s-{stateOf(b.node, mode)}"
            class:here={layerId === b.node.id}
            style="flex: {b.pct}"
            onclick={() => zoom(b.node)}
          >
            <span class="band"></span>
            <span class="tag" class:wide={b.pct >= 6}>
              <span class="tag-name">{b.pct >= 6 ? b.node.name : ''}</span>
              <span class="num">{fmtTokens(b.node.tokens)}</span>
            </span>
            <span class="vh">{b.node.name} {fmtTokens(b.node.tokens)}</span>
          </button>
        {/each}
      </div>

      {#if focus && focus !== root && (focus.summary || focus.note)}
        <p class="focus">
          <span>{focus.summary ?? focus.note}</span>
          <span class="focus-meta num">{metaBits(focus).join(' · ')}</span>
        </p>
      {/if}

      <div class="bar low">
        <nav class="crumbs" aria-label="위치">
          {#each trail as n, i}
            {#if i > 0}<span class="sep">›</span>{/if}
            {#if i === trail.length - 1}
              <span class="here">{n.name}</span>
            {:else}
              <button class="crumb" onclick={() => zoom(n)}>{n.name}</button>
            {/if}
          {/each}
          {#if trail.length > 1}<span class="esc">Esc 로 한 단계 위</span>{/if}
        </nav>
        <ul class="legend">
          {#each LEGENDS[mode] as [s, label]}
            <li><span class="dot s-{s}"></span>{label}</li>
          {/each}
          {#if withLazy}<li><span class="dot hatch"></span>지연 — 부르면 그때 실린다</li>{/if}
        </ul>
      </div>
    {/if}
  </header>

  <section class="stage">
    {#if state === 'loading'}
      <div class="pane"><p>지도를 읽는 중</p></div>
    {:else if state === 'error'}
      <div class="pane">
        <p class="bad">{error}</p>
        <p>`uv run scripts/map.py` 로 data/map.json 을 만든 뒤 다시 읽어라.</p>
        <button class="again" onclick={load}>다시 읽기</button>
      </div>
    {:else if state === 'empty'}
      <div class="pane">
        <p>지도가 비어 있다.</p>
        <p>data/map.json 에 층이 하나도 없다 — 재고를 먼저 갱신하라.</p>
        <button class="again" onclick={load}>다시 읽기</button>
      </div>
    {:else}
      <div class="split">
        <div class="mapwrap">
          <Treemap {focus} {mode} {selected} {spot} {marks} onzoom={zoom} onselect={pick} />
        </div>
        {#if showActions}
          <aside class="acts-panel">
            <header>
              <h2>실행 목록</h2>
              <button class="x" onclick={() => (showActions = false)} aria-label="닫기">✕</button>
            </header>
            {#if !actions.length}
              <p class="none">아직 고른 것이 없다. 노드를 골라 아래에서 「뺀다」나 「줄인다」를 찍어라.</p>
            {:else}
              <ul>
                {#each actions as a}
                  <li>
                    <p class="a-head">
                      <button class="a-name" onclick={() => { selected = a.id; showActions = false }}>{a.node.name}</button>
                      <span class="a-choice">{choiceLabel(a.choice)}</span>
                      <span class="num">{fmtTokens(a.node.tokens)}</span>
                    </p>
                    {#if a.card?.howto}<p class="a-how">{a.card.howto}</p>{/if}
                    {#if a.memo?.trim()}<p class="a-memo">{a.memo}</p>{/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </aside>
        {/if}
        {#if selNode}
          <Panel
            node={selNode}
            card={selCard}
            entry={notes[selNode.id]}
            {saving}
            onchoose={(c) => save({ choice: c })}
            onmemo={(m) => save({ memo: m })}
            onsay={(t) => save({ message: t })}
            {borrowed}
            onhover={(b) => (hoverBreak = b)}
            onzoom={zoom}
            onjump={jump}
            onclose={() => (selected = null)}
          />
        {/if}
      </div>
    {/if}
  </section>
</main>

<style>
  main {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    padding: var(--sp-6) var(--sp-8) var(--sp-6);
    max-width: 1680px;
    margin: 0 auto;
  }
  header { display: flex; flex-direction: column; gap: var(--sp-3); }

  .bar { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--sp-6); }
  .bar.low { align-items: center; }

  h1 { margin: 0; font-size: 20px; font-weight: 600; line-height: 1.3; }
  .sub { margin: 2px 0 0; font-size: 12.5px; color: var(--muted); }

  .modes { display: flex; gap: 2px; padding: 2px; background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r); }
  .modes button {
    padding: 5px var(--sp-3);
    font-size: 12.5px;
    background: none;
    border: 0;
    border-radius: 2px;
    color: var(--muted);
    cursor: pointer;
  }
  .modes button:hover { color: var(--text); background: var(--surface); }
  .modes button.on { color: var(--surface); background: var(--accent); }

  .totals { display: flex; align-items: baseline; gap: var(--sp-3); flex-wrap: wrap; }
  .big { font-size: 28px; font-weight: 600; line-height: 1.1; }
  .unit { font-size: 12.5px; color: var(--muted); margin-left: -6px; }
  .split { font-size: 12.5px; color: var(--muted); }
  .split b { font-weight: 600; color: var(--text); margin-right: var(--sp-3); }
  .lazy { font-size: 12.5px; color: var(--muted); }
  .lazy b { font-weight: 600; color: var(--text); }
  .lazy .off { margin-left: var(--sp-2); }
  .legend .hatch {
    background: var(--surface-2);
    border: 1px dashed var(--line-strong);
    background-image: repeating-linear-gradient(45deg, transparent 0 2px, var(--line-strong) 2px 3px);
  }
  .when { margin-left: auto; font-size: 12.5px; color: var(--muted); }
  .stale {
    font-size: 12.5px; color: var(--warn, #b06000);
    border: 1px solid currentColor; border-radius: 999px; padding: 1px 8px;
  }

  /* 띠 하나가 층의 몫을 그대로 보인다 — 지도의 눈금자. */
  .spine { display: flex; gap: 1px; align-items: stretch; }
  .seg {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 6px;
    padding: 0;
    background: none;
    border: 0;
    text-align: left;
    cursor: pointer;
    overflow: hidden;
  }
  .band { display: block; height: 6px; background: var(--edge); opacity: 0.5; }
  .seg:hover .band { opacity: 0.8; }
  .seg.here .band { opacity: 1; height: 8px; margin-top: -2px; }
  .tag {
    display: flex;
    gap: var(--sp-2);
    padding-left: 1px;
    font-size: 12.5px;
    color: var(--muted);
    white-space: nowrap;
  }
  .tag .num { color: var(--text); }
  .tag:not(.wide) .num { color: var(--muted); }
  .seg.here .tag-name { color: var(--text); font-weight: 600; }

  .focus {
    display: flex;
    align-items: baseline;
    gap: var(--sp-3) var(--sp-4);
    flex-wrap: wrap;
    margin: 0;
    font-size: 12.5px;
    color: var(--text);
  }
  .focus-meta { color: var(--muted); }

  .crumbs { display: flex; align-items: center; gap: var(--sp-2); font-size: 12.5px; min-height: 22px; }
  .crumb { padding: 0; background: none; border: 0; color: var(--accent); cursor: pointer; }
  .crumb:hover { text-decoration: underline; }
  .crumbs .here { font-weight: 600; }
  .sep { color: var(--line-strong); }
  .esc { margin-left: var(--sp-2); color: var(--muted); }

  .legend { display: flex; flex-wrap: wrap; gap: var(--sp-1) var(--sp-4); margin: 0; padding: 0; list-style: none; font-size: 12.5px; color: var(--muted); }

  .stage { flex: 1; min-height: 360px; }
  .split { display: flex; gap: var(--sp-3); height: 100%; }
  .mapwrap { flex: 1; min-width: 0; }

  .tools { display: flex; align-items: center; gap: var(--sp-3); }
  .tally { margin: 0; font-size: 12.5px; color: var(--muted); }
  .acts {
    padding: 5px var(--sp-3);
    font-size: 12.5px;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    cursor: pointer;
  }
  .acts:hover { background: var(--surface-2); }
  .acts.on { background: var(--text); border-color: var(--text); color: var(--surface); }

  .acts-panel {
    width: 340px;
    flex: none;
    padding: var(--sp-3) var(--sp-4) var(--sp-4);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r);
    overflow-y: auto;
  }
  .acts-panel header { display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: var(--sp-2); }
  .acts-panel h2 { margin: 0; font-size: 14px; font-weight: 600; }
  .acts-panel .x { padding: 2px 6px; background: none; border: 0; color: var(--muted); cursor: pointer; }
  .acts-panel .none { margin: var(--sp-3) 0 0; font-size: 12.5px; color: var(--muted); line-height: 1.6; }
  .acts-panel ul { margin: var(--sp-3) 0 0; padding: 0; list-style: none; }
  .acts-panel li { padding: var(--sp-2) 0; border-top: 1px solid var(--line); }
  .a-head { display: flex; align-items: baseline; gap: var(--sp-2); margin: 0; font-size: 12.5px; }
  .a-name { flex: 1; padding: 0; text-align: left; background: none; border: 0; color: var(--accent); cursor: pointer; overflow-wrap: anywhere; }
  .a-name:hover { text-decoration: underline; }
  .a-choice { font-weight: 600; }
  .a-how { margin: var(--sp-1) 0 0; font-size: 12.5px; color: var(--muted); overflow-wrap: anywhere; }
  .a-memo { margin: var(--sp-1) 0 0; font-size: 12.5px; }
  .pane {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r);
    color: var(--muted);
  }
  .pane p { margin: 0; }
  .pane .bad { color: var(--idle); font-weight: 600; }
  .again {
    margin-top: var(--sp-2);
    padding: 6px var(--sp-3);
    font-size: 12.5px;
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    cursor: pointer;
  }
  .again:hover { background: var(--surface-2); }

  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 2px;
    margin-right: 6px;
    background: var(--edge);
  }
  .split .dot { margin-left: var(--sp-2); }

  .s-open, .s-improve { --edge: var(--accent); }
  .s-fixed, .s-unknown, .s-none { --edge: var(--stone); }
  .s-live, .s-keep { --edge: var(--live); }
  .s-hold, .s-update, .s-hook { --edge: var(--hold); }
  .s-idle, .s-retire { --edge: var(--idle); }
  .s-merge { --edge: var(--merge); }

  .vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }

  @media (max-width: 720px) {
    main { padding: var(--sp-4); }
    .bar { flex-direction: column; gap: var(--sp-3); }
    .when { margin-left: 0; }
  }
</style>
