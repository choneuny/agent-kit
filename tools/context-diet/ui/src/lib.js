// 지도의 순수 로직 — 넓이 계산과 색 판정. 화면 없이 check.mjs로 돌려 볼 수 있다.

/* ── squarified treemap ────────────────────────────────────────────────
   items: [{ value, node }] · rect: {x,y,w,h} → [{ node, x, y, w, h }]
   값이 0 이하인 것은 넣지 않는다 — 넓이 0은 타일이 될 수 없다. */
export function squarify(items, rect) {
  const list = items.filter((i) => i.value > 0).sort((a, b) => b.value - a.value)
  const out = []
  if (!list.length || rect.w <= 0 || rect.h <= 0) return out

  let { x, y, w, h } = rect
  let left = list.reduce((s, i) => s + i.value, 0)
  let i = 0

  while (i < list.length && w > 0 && h > 0) {
    const side = Math.min(w, h)
    const scale = (w * h) / left
    let row = [list[i]]
    let sum = list[i].value
    let best = worstRatio(row, sum, side, scale)
    let j = i + 1
    while (j < list.length) {
      const next = sum + list[j].value
      const cand = worstRatio([...row, list[j]], next, side, scale)
      if (cand > best) break
      row.push(list[j]); sum = next; best = cand; j++
    }
    const area = sum * scale
    if (w >= h) {
      const rw = Math.min(area / h, w)
      let cy = y
      for (const it of row) {
        const ih = (it.value * scale) / rw
        out.push({ node: it.node, x, y: cy, w: rw, h: ih })
        cy += ih
      }
      x += rw; w -= rw
    } else {
      const rh = Math.min(area / w, h)
      let cx = x
      for (const it of row) {
        const iw = (it.value * scale) / rh
        out.push({ node: it.node, x: cx, y, w: iw, h: rh })
        cx += iw
      }
      y += rh; h -= rh
    }
    left -= sum
    i = j
  }
  return out
}

function worstRatio(row, sum, side, scale) {
  const area = sum * scale
  const max = row[0].value * scale
  const min = row[row.length - 1].value * scale
  const s2 = side * side
  return Math.max((s2 * max) / (area * area), (area * area) / (s2 * min))
}

/* ── 중첩 배치 ─────────────────────────────────────────────────────────
   focus 노드를 rect에 채우고 maxDepth까지 자식을 안쪽에 깐다.
   묶음 타일은 위쪽에 이름줄만큼 자리를 비워 둔다. */
export function layoutTree(focus, rect, opts = {}) {
  const { maxDepth = 2, header = 28, subHeader = 22, pad = 5, min = 28, headerFor = null } = opts
  const out = []
  place(focus, rect, 0)
  return out

  function place(node, r, depth) {
    let kids = (node.children || []).filter((c) => c.tokens > 0)
    const hidden = (node.children || []).length - kids.length // 0 토큰이라 자리를 못 받은 것
    // 이름이 같은 외자식은 한 겹을 더 그릴 값이 없다
    if (kids.length === 1 && kids[0].name === node.name) kids = []
    const cell = { node, depth, x: r.x, y: r.y, w: r.w, h: r.h, leaf: true, hidden }
    out.push(cell)
    if (!kids.length || depth >= maxDepth) return
    const hd = depth === 0 ? header : (headerFor ? headerFor(node, r, depth) : subHeader)
    const inner = { x: r.x + pad, y: r.y + hd, w: r.w - pad * 2, h: r.h - hd - pad }
    if (inner.w < min || inner.h < min) return
    cell.leaf = false
    for (const c of squarify(kids.map((k) => ({ value: k.tokens, node: k })), inner)) {
      place(c.node, { x: c.x, y: c.y, w: c.w, h: c.h }, depth + 1)
    }
  }
}

/* ── 노드 집계 ───────────────────────────────────────────────────────── */
export function leaves(node, out = []) {
  if (node.children && node.children.length) node.children.forEach((c) => leaves(c, out))
  else out.push(node)
  return out
}

export function controlState(node) {
  return node.fixed ? 'fixed' : 'open'
}

/** 호출로 셀 수 있는 것 — 나머지(규칙·메모리·시스템)는 부르는 것이 아니라 늘 실린다. */
export const COUNTABLE = new Set(['skill', 'command', 'agent', 'mcp', 'mcp_tool'])

/** 쓰임: 기록이 없는 것과 세지 않는 것을 나눈다. 기록 없는 호출 대상은 0회다. */
export function usageState(node) {
  if (node.kind === 'hook') return 'hook'
  if (!COUNTABLE.has(node.kind)) return 'unknown'
  const calls = node.usage?.calls_30d ?? 0
  if (calls > 0) return 'live'
  if (isNew(node)) return 'hold'
  return 'idle'
}

/** 설치 30일 미만이면 안 쓴다는 판정을 보류한다. 설치 시각을 모르면 보류하지 않는다. */
export function isNew(node, now = Date.now()) {
  if (!node.installed_at) return false
  const t = Date.parse(node.installed_at)
  return Number.isFinite(t) && now - t < 30 * 864e5
}

export function verdictState(node) {
  const v = node.verdict
  if (!v) return 'none'
  const s = v.toLowerCase()
  return s.startsWith('merge') ? 'merge' : s
}

const PICK = { control: controlState, usage: usageState, verdict: verdictState }

/** 잎 하나면 제 상태, 묶음이면 토큰이 가장 무거운 상태. */
export function stateOf(node, mode) {
  const pick = PICK[mode]
  const kids = leaves(node)
  if (kids.length === 1) return pick(kids[0])
  const weight = new Map()
  for (const l of kids) {
    const s = pick(l)
    weight.set(s, (weight.get(s) || 0) + Math.max(l.tokens, 1))
  }
  let top = 'none'
  let best = -1
  for (const [k, v] of weight) if (v > best) { top = k; best = v }
  return top
}

/** 묶음 타일의 상태 구성 — 툴팁에서 「무엇이 섞여 있나」를 보인다. */
export function mixOf(node, mode) {
  const pick = PICK[mode]
  const weight = new Map()
  for (const l of leaves(node)) {
    const s = pick(l)
    weight.set(s, (weight.get(s) || 0) + l.tokens)
  }
  return [...weight].sort((a, b) => b[1] - a[1])
}

export const MODES = [['control', '고정·조절'], ['usage', '쓰임'], ['verdict', '판정']]

export const LEGENDS = {
  control: [['open', '조절 가능'], ['fixed', '고정']],
  usage: [['live', '쓰고 있음'], ['idle', '안 쓰임'], ['hold', '보류 (설치 30일 미만)'],
    ['hook', '훅이 부름'], ['unknown', '세지 않음 (늘 실림)']],
  verdict: [['keep', 'Keep'], ['improve', 'Improve'], ['update', 'Update'],
    ['retire', 'Retire'], ['merge', 'Merge into X'], ['none', '판정 없음']],
}

export const LABELS = Object.fromEntries(
  Object.values(LEGENDS).flat().map(([k, v]) => [k, v])
)

/* ── 표기 ───────────────────────────────────────────────────────────── */
export function fmtTokens(n) {
  if (n == null) return '–'
  if (n === 0) return '0'
  if (n < 1000) return String(n)
  return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k'
}

export function fmtDate(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(+d)) return null
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}`
}

export function fmtAgo(iso, now = Date.now()) {
  const d = fmtDate(iso)
  if (!d) return null
  const days = Math.floor((now - Date.parse(iso)) / 864e5)
  if (days <= 0) return `${d} · 오늘`
  return `${d} · ${days}일 전`
}

/* ── 결정 카드와의 이음 ─────────────────────────────────────────────── */

/** 노드에 걸린 카드 — 제 id로 먼저, 없으면 속한 단위(unit_id)로. */
export function cardFor(node, cards) {
  if (!node || !cards) return null
  return cards.get(node.id) ?? (node.unit_id ? cards.get(node.unit_id) : null) ?? null
}

export const CHOICES = { keep: '둔다', remove: '뺀다', shrink: '줄인다', hold: '보류' }

export function choiceLabel(c) {
  if (!c) return null
  if (c.startsWith('merge:')) return `${c.slice(6)}에 합친다`
  return CHOICES[c] ?? c
}

/** 이름과 id로 노드를 찾는 표. 「빼면 깨지는 것」의 상대를 지도에서 찾을 때 쓴다. */
export function nodeIndex(root, out = { byName: new Map(), byId: new Map() }) {
  if (!out.byName.has(root.name)) out.byName.set(root.name, root)
  out.byId.set(root.id, root)
  for (const c of root.children || []) nodeIndex(c, out)
  return out
}

/** 카드가 `target_id`를 담으면 그것으로 찾고, 없을 때만 이름을 되짚는다.
    ponytail: 이름 되짚기는 겹치면 첫 번째를 쓴다 — 카드가 id를 다 담으면 지워도 된다. */
export function breakTarget(b, index) {
  if (!b || !index) return null
  const id = typeof b === 'string' ? null : b.target_id
  if (id && index.byId.has(id)) return index.byId.get(id)
  const what = typeof b === 'string' ? b : b.what
  if (!what) return null
  const words = what.trim().split(/\s+/)
  for (let i = 0; i < words.length; i++) {
    const tail = words.slice(i).join(' ')
    if (index.byName.has(tail)) return index.byName.get(tail)
  }
  return null
}

/** 머리에 거는 집계 — 주석·뺀다·줄인다. */
export function counts(state) {
  let memo = 0, remove = 0, shrink = 0
  for (const v of Object.values(state || {})) {
    if (v?.memo?.trim() || v?.thread?.length) memo++
    if (v?.choice === 'remove') remove++
    if (v?.choice === 'shrink' || v?.choice?.startsWith?.('merge:')) shrink++
  }
  return { memo, remove, shrink }
}

/** MCP 도구는 제 호출 기록이 없다 — 서버 것을 물려받아 쓰고, 어디서 왔는지 남긴다. */
export function inheritUsage(node, from = null) {
  if (!node.usage && from?.usage) {
    node.usage = from.usage
    node.usage_from = from.name
  }
  for (const c of node.children || []) inheritUsage(c, node.usage && !node.usage_from ? node : from)
  return node
}

/** 노드의 흔적 한 줄 — 타일에도 머리에도 같은 것을 쓴다. */
export function metaBits(n, withTok = true) {
  const b = []
  if (withTok) b.push(fmtTokens(n.tokens) + ' 토큰')
  if (n.children?.length) b.push(`구성 ${n.children.length}개`)
  if (COUNTABLE.has(n.kind)) b.push(`30일 ${n.usage?.calls_30d ?? 0}회`)
  if (n.installed_at) b.push(fmtDate(n.installed_at) + ' 처음')
  if (n.verdict) b.push(n.verdict + (n.merge_into ? ` → ${n.merge_into}` : ''))
  return b
}

/** 설치 시각을 어디서 얻었나 — 「보류」가 붙는 근거를 노드마다 밝힌다. */
export const INSTALL_SOURCE = {
  'transcript-first': '기록에 처음 나온 날',
  'agents-git': 'git 첫 커밋',
  'plugin-meta': '플러그인 메타',
  'file-birth': '파일 생성 시각',
  'file-mtime': '파일 수정 시각',
}

/** 머리의 띠: 층마다 한 칸. */
export function spine(root) {
  const total = root.tokens || 1
  return (root.children || []).map((c) => ({ node: c, pct: (c.tokens / total) * 100 }))
}

/** 지연 로드 — 이름만 실리고 부를 때 본문이 온다. 맨 위 지연 노드의 토큰만 센다. */
export function deferredTokens(node) {
  if (node.deferred) return node.tokens || 0
  return (node.children || []).reduce((s, c) => s + deferredTokens(c), 0)
}

/** 지연을 뺀 나무 — 세션 시작에 실리는 것만. 남은 자식으로 토큰을 다시 더한다. */
export function residentOnly(node) {
  if (node.deferred) return null
  if (!node.children?.length) return node
  const kids = node.children.map(residentOnly).filter(Boolean)
  return { ...node, children: kids, tokens: kids.reduce((s, k) => s + k.tokens, 0) }
}

export function totals(root) {
  let fixed = 0
  for (const l of leaves(root)) if (l.fixed) fixed += l.tokens
  return { total: root.tokens, fixed, open: root.tokens - fixed }
}

/** 뿌리에서 노드까지의 길 — 빵부스러기용. */
export function pathTo(root, id, trail = []) {
  const next = [...trail, root]
  if (root.id === id) return next
  for (const c of root.children || []) {
    const found = pathTo(c, id, next)
    if (found) return found
  }
  return null
}
