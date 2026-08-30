<script>
  import { layoutTree, stateOf, mixOf, fmtTokens, fmtDate, fmtAgo, LABELS, INSTALL_SOURCE, COUNTABLE, metaBits } from './lib.js'

  let { focus, mode, selected = null, spot = null, marks = null, onzoom, onselect } = $props()

  let box = $state({ w: 0, h: 0 })
  let hover = $state(null) // { cell, x, y }

  const cells = $derived(
    box.w > 40 && box.h > 40
      ? layoutTree(focus, { x: 0, y: 0, w: box.w, h: box.h }, { maxDepth: 3, header: 5, headerFor })
      : []
  )

  // 밝힐 상대가 지금 화면에 하나도 없으면 아무것도 흐리지 않는다
  const lit = $derived(spot ? cells.filter((c) => spot.has(c.node.id)).length : 0)

  // 글자 폭 어림 — 들어가지 않으면 자르지 않고 생략한다.
  function width(text, size) {
    let px = 0
    for (const ch of text) px += /[\uAC00-\uD7A3\u3131-\u318E\u4E00-\u9FFF]/.test(ch) ? size : size * 0.56
    return px
  }

  /** 타일에 보이는 이름 — 지연이면 꼬리표만큼 자리를 더 잡는다. */
  function shown(n) {
    return n.deferred ? `${n.name} 지연` : n.name
  }

  /** 묶음 타일의 이름줄 높이 — 이름이 접히는 만큼 자리를 준다(최대 세 줄). */
  function headerFor(node, r, depth) {
    const size = depth === 1 ? 14 : 12.5
    const lineH = size === 14 ? 20 : 18
    const inner = r.w - 16
    if (inner < 30 || longest(shown(node), size) > inner) return 22
    const lines = Math.min(3, Math.ceil(width(shown(node), size) / inner))
    const want = lines * lineH + 6
    return want > r.h * 0.45 ? 22 : want
  }

  /** 줄바꿈이 안 되는 가장 긴 토막 — 이만큼도 안 들어가면 글자가 잘린다. */
  function longest(text, size) {
    return Math.max(...text.split(/[\s\-_.:/()]+/).map((w) => width(w, size)), 0)
  }

  /** 타일에 실을 것을 넓이에 따라 단계로 정한다: 이름 → +토큰 → +요약 → +흔적. */
  function content(cell) {
    const n = cell.node
    const inner = cell.w - 16
    if (inner < 30) return null

    const size = cell.depth === 1 ? 14 : 12.5
    const lineH = size === 14 ? 20 : 18
    const nameW = width(shown(n), size)
    const tokW = width(fmtTokens(n.tokens), 12.5) + 10

    // 묶음은 이름줄 한 줄뿐이다 — 아래는 자식이 덮는다
    if (!cell.leaf) {
      if (longest(shown(n), size) > inner) return null
      const lines = Math.ceil(nameW / inner)
      if (lines > 3) return null
      return { lines, tok: lines === 1 && nameW + tokW <= inner, sum: null, meta: null }
    }

    const lines = Math.ceil(nameW / inner)
    if (lines > 2 || cell.h < lines * lineH + 8 || longest(shown(n), size) > inner) return null
    let used = lines * lineH + 8
    const tok = lines === 1 && nameW + tokW <= inner

    // 요약: 줄 수를 어림해 들어갈 때만
    let sum = null
    if (n.summary && inner >= 120) {
      const need = Math.ceil(width(n.summary, 12.5) / inner)
      if (need <= 5 && cell.h >= used + need * 17 + 10) { sum = n.summary; used += need * 17 + 8 }
    }

    // 흔적 한 줄: 안 들어가는 조각은 뒤에서 하나씩 뺀다
    let meta = null
    if (cell.h >= used + 18) {
      const bits = metaBits(n, !tok)
      while (bits.length && width(bits.join(' · '), 12.5) > inner) bits.pop()
      if (bits.length) meta = bits.join(' · ')
    }
    return { lines, tok, sum, meta }
  }

  function tone(node) {
    return stateOf(node, mode)
  }

  // 자식이 그려진 타일(이름줄)만 줌한다. 잎으로 그려진 것은 고르기만 —
  // 그래야 지도가 그대로 있어 「빼면 깨지는 것」이 어디 있는지 보인다.
  function open(cell) {
    if (cell.depth === 0) return
    if (!cell.leaf) onzoom?.(cell.node)
    else onselect?.(cell.node)
  }

  const TIP = { w: 288, h: 240 }
  function move(cell, e) {
    // 창 밖으로 나가면 반대쪽으로 넘긴다
    const vw = window.innerWidth
    const vh = window.innerHeight
    const x = e.clientX + 16 + TIP.w > vw ? e.clientX - 16 - TIP.w : e.clientX + 16
    const y = e.clientY + 16 + TIP.h > vh ? Math.max(8, e.clientY - 16 - TIP.h) : e.clientY + 16
    hover = { cell, x, y }
  }
</script>

<div class="map" bind:clientWidth={box.w} bind:clientHeight={box.h}>
  {#each cells as cell (cell.node.id)}
    {@const n = cell.node}
    {@const t = tone(n)}
    {@const label = fmtTokens(n.tokens)}
    <button
      class="tile s-{t}"
      class:group={!cell.leaf}
      class:lay={cell.depth === 1}
      class:root={cell.depth === 0}
      class:sel={selected === n.id}
      class:tiny={cell.w < 26 || cell.h < 22}
      class:dim={lit > 0 && cell.leaf && !spot.has(n.id) && n.id !== selected}
      class:lit={spot?.has(n.id)}
      class:lazy={n.deferred}
      style="left:{cell.x}px; top:{cell.y}px; width:{cell.w}px; height:{cell.h}px"
      onclick={() => open(cell)}
      onmousemove={(e) => move(cell, e)}
      onmouseleave={() => (hover = null)}
      onfocus={() => move(cell, { clientX: cell.x + 40, clientY: cell.y + 40 })}
      onblur={() => (hover = null)}
      disabled={cell.depth === 0}
      aria-label="{n.name} {label} 토큰{n.deferred ? ' · 지연 로드' : ''}"
    >
      {#if cell.depth > 0}
        {@const c = content(cell)}
        {#if c}
          <span class="head">
            <span class="name">{n.name}{#if n.deferred}<span class="lz">지연</span>{/if}</span>
            {#if c.tok}<span class="tok num">{label}</span>{/if}
          </span>
          {#if c.sum}<span class="sum">{c.sum}</span>{/if}
          {#if c.meta}<span class="meta num">{c.meta}</span>{/if}
        {/if}
      {/if}
      {#if n.flags?.length && cell.w >= 44 && cell.h >= 26}<span class="flag" aria-hidden="true"></span>{/if}
      {#if marks?.has(n.id) && cell.w >= 20 && cell.h >= 16}
        {@const mk = marks.get(n.id)}
        <span class="mark" class:choice={mk.choice} title={mk.title} aria-hidden="true"></span>
      {/if}
    </button>
  {/each}

  {#if !cells.length}
    <p class="thin">지도를 그릴 자리가 좁다 — 창을 넓혀라.</p>
  {/if}
</div>

{#if hover}
  {@const n = hover.cell.node}
  {@const t = tone(n)}
  <div
    class="tip"
    style="left:{hover.x}px; top:{hover.y}px"
  >
    <p class="tip-name">{n.name}</p>
    <dl>
      <dt>토큰</dt><dd class="num">{fmtTokens(n.tokens)}{n.basis === 'estimated' ? ' (추정값)' : ''}</dd>
      {#if n.body_tokens != null && n.body_tokens !== n.tokens}
        <dt>본문</dt><dd class="num">{fmtTokens(n.body_tokens)}</dd>
      {/if}
      <dt>{mode === 'verdict' ? '판정' : mode === 'usage' ? '쓰임' : '구분'}</dt>
      <dd><span class="dot s-{t}"></span>{LABELS[t] ?? t}{n.merge_into ? ` → ${n.merge_into}` : ''}</dd>
      {#if n.usage?.calls_30d != null}
        <dt>30일</dt><dd class="num">{n.usage_from ? `${n.usage_from} 기준 ` : ''}{n.usage.calls_30d}회{n.usage.calls_7d != null ? ` · 7일 ${n.usage.calls_7d}회` : ''}</dd>
      {:else if COUNTABLE.has(n.kind)}
        <dt>30일</dt><dd>부른 기록 없음</dd>
      {/if}
      {#if n.usage?.last_used}
        <dt>마지막</dt><dd>{fmtAgo(n.usage.last_used)}</dd>
      {/if}
      {#if n.installed_at}
      <dt>설치</dt>
      <dd>
        {fmtAgo(n.installed_at) ?? '모름'}
        {#if n.installed_source}<span class="weak">{INSTALL_SOURCE[n.installed_source] ?? n.installed_source}</span>{/if}
      </dd>
      {/if}
      {#if hover.cell.node.children?.length}
        <dt>구성</dt>
        <dd>{n.children.length}개{hover.cell.hidden ? ` · 0 토큰 ${hover.cell.hidden}개` : ''}</dd>
      {/if}
    </dl>
    {#if n.deferred}<p class="tip-lazy">부르면 그때 실린다 — 평소엔 이름 한 줄</p>{/if}
    {#if n.summary}<p class="tip-sum">{n.summary}</p>{/if}
    {#if !n.summary && n.note}<p class="tip-sum">{n.note}</p>{/if}
    {#if n.flags?.length}<p class="tip-flag">{n.flags.join(' · ')}</p>{/if}
    {#if mixOf(n, mode).length > 1}
      <p class="tip-mix">
        {#each mixOf(n, mode).slice(0, 4) as [s, v]}
          <span class="mix"><span class="dot s-{s}"></span>{LABELS[s] ?? s} <b class="num">{fmtTokens(v)}</b></span>
        {/each}
      </p>
    {/if}
    <p class="tip-go">{n.children?.length ? '눌러서 안으로' : '눌러서 고름'}</p>
  </div>
{/if}

<style>
  .map {
    position: relative;
    height: 100%;
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--r);
    overflow: hidden;
  }

  .tile {
    position: absolute;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    margin: 0;
    padding: 0;
    text-align: left;
    background: var(--fill);
    border: 1px solid var(--edge-soft);
    border-top: 2px solid var(--edge);
    border-radius: 2px;
    cursor: pointer;
    overflow: hidden;
    transition: filter 90ms linear, box-shadow 90ms linear;
  }
  .tile.group {
    background: var(--surface);
    border-color: var(--line);
    border-top-color: var(--edge);
  }
  .tile.tiny { border-top-width: 1px; border-top-color: var(--edge-soft); }
  .tile.root {
    background: var(--surface-2);
    border: 0;
    border-radius: 0;
    cursor: default;
  }
  .tile:not(.root):hover { filter: brightness(0.965); box-shadow: inset 0 0 0 1px var(--edge); }
  .tile.sel { box-shadow: inset 0 0 0 2px var(--edge); }
  .tile:disabled { cursor: default; }

  .head {
    display: flex;
    flex: none;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--sp-2);
    padding: 3px var(--sp-2) 0;
    line-height: 1.35;
    pointer-events: none;
  }
  .name { font-size: 12.5px; color: var(--text); }
  .group > .head .name { font-size: 12.5px; font-weight: 600; color: var(--muted); }
  .group.lay > .head .name { font-size: 14px; color: var(--text); }
  .tok { font-size: 12.5px; color: var(--muted); flex: none; }
  .sum {
    padding: 3px var(--sp-2) 0;
    font-size: 12.5px;
    line-height: 1.35;
    color: var(--text);
    opacity: 0.78;
    pointer-events: none;
  }
  .meta {
    padding: 4px var(--sp-2) 0;
    font-size: 12.5px;
    line-height: 1.35;
    color: var(--muted);
    pointer-events: none;
  }

  .flag {
    position: absolute;
    pointer-events: none;
    top: 0;
    right: 0;
    border-top: 9px solid var(--hold);
    border-left: 9px solid transparent;
  }

  /* 지연 로드: 빗금과 점선 테두리 — 색 모드가 무엇이든 그대로 남는다 */
  .tile.lazy {
    background-image: repeating-linear-gradient(45deg,
      transparent 0 5px,
      color-mix(in srgb, var(--edge) 20%, transparent) 5px 7px);
    border-style: dashed;
    border-top-style: solid;
  }
  .lz {
    display: inline-block;
    white-space: nowrap;
    margin-left: 5px;
    padding: 0 4px;
    font-size: 12.5px;
    color: var(--muted);
    border: 1px dashed var(--line-strong);
    border-radius: 2px;
  }

  .tile.dim { opacity: 0.32; }
  .tile.lit { box-shadow: 0 0 0 3px var(--hold); z-index: 5; }

  /* 주석 표시: 메모만 있으면 빈 점, 선택까지 찍혔으면 채운 점 */
  .mark {
    position: absolute;
    left: 4px;
    bottom: 4px;
    width: 7px;
    height: 7px;
    border: 1.5px solid var(--text);
    border-radius: 50%;
    background: var(--surface);
    pointer-events: none;
  }
  .mark.choice { background: var(--text); }

  .thin { padding: var(--sp-4); color: var(--muted); }

  /* 색은 모드가 정한다 */
  .s-open,   .s-improve { --fill: var(--f-accent); --edge: var(--accent); }
  .s-fixed,  .s-unknown, .s-none { --fill: var(--f-stone); --edge: var(--stone); }
  .s-live,   .s-keep { --fill: var(--f-live); --edge: var(--live); }
  .s-hold,   .s-update, .s-hook { --fill: var(--f-hold); --edge: var(--hold); }
  .s-idle,   .s-retire { --fill: var(--f-idle); --edge: var(--idle); }
  .s-merge { --fill: var(--f-merge); --edge: var(--merge); }
  .tile { --edge-soft: color-mix(in srgb, var(--edge) 28%, transparent); }

  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 2px;
    margin-right: 6px;
    background: var(--edge);
    vertical-align: baseline;
  }

  .tip {
    position: fixed;
    z-index: 20;
    width: 288px;
    padding: var(--sp-3);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: var(--r);
    box-shadow: 0 6px 18px rgb(20 18 10 / 12%);
    pointer-events: none;
  }
  .tip-name { margin: 0 0 var(--sp-2); font-size: 14px; font-weight: 600; line-height: 1.4; }
  .tip dl {
    display: grid;
    grid-template-columns: 58px 1fr;
    gap: 2px var(--sp-2);
    margin: 0;
    font-size: 12.5px;
  }
  .tip dt { color: var(--muted); }
  .tip dd { margin: 0; }
  .tip .weak { display: block; color: var(--muted); }
  .tip-sum {
    margin: var(--sp-2) 0 0;
    padding-top: var(--sp-2);
    border-top: 1px solid var(--line);
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--text);
  }
  .tip-lazy { margin: var(--sp-2) 0 0; font-size: 12.5px; color: var(--muted); }
  .tip-flag { margin: var(--sp-2) 0 0; font-size: 12.5px; color: var(--hold); }
  .tip-mix { display: flex; flex-wrap: wrap; gap: 2px var(--sp-3); margin: var(--sp-2) 0 0; font-size: 12.5px; color: var(--muted); }
  .tip-mix b { font-weight: 600; color: var(--text); }
  .tip-go { margin: var(--sp-2) 0 0; font-size: 12.5px; color: var(--muted); }
</style>
