// node check.mjs — 넓이 계산을 실물 지도로 한 번 돌려 본다.
// 보는 것 둘: 넓이가 토큰에 비례하는가, 형제 타일이 겹치지 않는가.
import { readFileSync, existsSync } from 'node:fs'
import assert from 'node:assert/strict'
import { squarify, layoutTree, leaves, stateOf, totals, fmtTokens, fmtAgo, nodeIndex, breakTarget,
  deferredTokens, residentOnly } from './src/lib.js'

const FILE = '../data/map.json'
assert.ok(existsSync(FILE), 'data/map.json 이 없다 — uv run scripts/map.py 를 먼저 돌려라')
const { root } = JSON.parse(readFileSync(FILE, 'utf8'))

/* 넓이 합 = 사각형 넓이, 그리고 각 타일 넓이 ∝ 토큰 */
{
  const rect = { x: 0, y: 0, w: 1200, h: 700 }
  const items = root.children.map((c) => ({ value: c.tokens, node: c }))
  const cells = squarify(items, rect)
  assert.equal(cells.length, items.filter((i) => i.value > 0).length, '토큰이 있는 것은 모두 자리를 받는다')

  const area = cells.reduce((s, c) => s + c.w * c.h, 0)
  assert.ok(Math.abs(area - rect.w * rect.h) / (rect.w * rect.h) < 1e-6, `넓이 합이 어긋난다: ${area}`)

  const total = items.reduce((s, i) => s + i.value, 0)
  for (const c of cells) {
    const want = (c.node.tokens / total) * rect.w * rect.h
    assert.ok(Math.abs(c.w * c.h - want) / want < 1e-6, `${c.node.name} 넓이가 토큰과 안 맞는다`)
    assert.ok(c.w > 0 && c.h > 0)
  }
  for (const [a, b] of pairs(cells)) assert.ok(!overlap(a, b), `${a.node.name}·${b.node.name} 겹침`)
}

/* 중첩 배치: 같은 부모의 자식끼리 안 겹치고, 자식은 부모 안에 든다 */
{
  const cells = layoutTree(root, { x: 0, y: 0, w: 1440, h: 720 }, { maxDepth: 2 })
  assert.ok(cells.length >= 25, `타일이 너무 적다: ${cells.length}`)  // 지금 30장
  const byParent = new Map()
  const box = new Map()
  for (const c of cells) box.set(c.node.id, c)
  for (const c of cells) {
    if (!c.leaf) for (const k of c.node.children || []) if (box.has(k.id)) push(byParent, c.node.id, box.get(k.id))
  }
  for (const [pid, kids] of byParent) {
    const p = box.get(pid)
    for (const k of kids) {
      assert.ok(k.x >= p.x - 0.01 && k.y >= p.y - 0.01 &&
        k.x + k.w <= p.x + p.w + 0.01 && k.y + k.h <= p.y + p.h + 0.01,
        `${k.node.name} 이 ${p.node.name} 밖으로 나갔다`)
    }
    for (const [a, b] of pairs(kids)) assert.ok(!overlap(a, b), `${a.node.name}·${b.node.name} 겹침`)
  }
}

/* 좁은 자리에서는 더 파고들지 않는다 */
{
  const small = layoutTree(root, { x: 0, y: 0, w: 200, h: 120 }, { maxDepth: 2 })
  assert.ok(small.every((c) => c.w >= 0 && c.h >= 0))
  assert.ok(small.length < 40, '좁은데도 타일을 너무 많이 깠다')
}

/* 집계와 표기 */
{
  const t = totals(root)
  assert.equal(t.fixed + t.open, t.total)
  assert.ok(t.fixed > 0 && t.open > 0)
  assert.equal(leaves(root).length >= root.children.length, true)
  assert.ok(['fixed', 'open'].includes(stateOf(root.children[0], 'control')))
  assert.equal(fmtTokens(152832), '153k')
  assert.equal(fmtTokens(5800), '5.8k')
  assert.equal(fmtTokens(0), '0')
  assert.equal(fmtTokens(null), '–')
  assert.equal(fmtAgo(null), null)
  // 설치 시각을 모르면 보류로 부르지 않는다
  assert.equal(stateOf({ kind: 'skill', tokens: 1, usage: { calls_30d: 0 }, installed_at: null }, 'usage'), 'idle')
}

/* 지연 로드: 상주만 = 전체 − 지연, 그리고 상주 나무에 지연 노드가 하나도 없다 */
{
  const lazy = deferredTokens(root)
  const res = residentOnly(root)
  assert.ok(lazy > 0, '지연 노드가 하나도 없다 — map.json 에 deferred 가 빠졌나')
  assert.equal(res.tokens, root.tokens - lazy, `상주 합이 안 맞는다: ${res.tokens} ≠ ${root.tokens} − ${lazy}`)
  assert.equal(countDeferred(res), 0, '상주 나무에 지연 노드가 남았다')
  assert.ok(countDeferred(root) >= 8, `지연 노드가 너무 적다: ${countDeferred(root)}`)
  // 층 띠도 상주 기준으로 다시 서야 한다
  for (const c of res.children) {
    const orig = root.children.find((o) => o.id === c.id)
    assert.equal(c.tokens, orig.tokens - deferredTokens(orig), `${c.name} 층의 상주 합이 안 맞는다`)
  }
  // 나무가 통째로 지연인 층은 없다 — 있으면 넓이 0 타일이 생긴다
  assert.ok(res.children.every((c) => c.tokens > 0), '상주만 모드에서 넓이 0 인 층이 생긴다')
  assert.ok(layoutTree(res, { x: 0, y: 0, w: 1440, h: 720 }, { maxDepth: 2 }).length > 20)
}

/* 「빼면 깨지는 것」의 상대 찾기: id가 있으면 id, 없으면 이름 되짚기 */
{
  const idx = nodeIndex(root)
  const some = [...idx.byId.keys()].find((k) => k.startsWith('rule:'))
  const named = idx.byId.get(some)
  assert.equal(breakTarget({ target_id: some, what: '엉뚱한 이름' }, idx).id, some, 'id가 이름을 이긴다')
  assert.equal(breakTarget({ what: `규칙 ${named.name}` }, idx).id, some, '이름 되짚기가 뒤를 받친다')
  assert.equal(breakTarget({ target_id: 'no:such', what: '없는 것' }, idx), null, '못 찾으면 null')
  assert.equal(breakTarget(null, idx), null)
}

function countDeferred(n) {
  return (n.deferred ? 1 : 0) + (n.children || []).reduce((s, c) => s + countDeferred(c), 0)
}
function pairs(xs) {
  const out = []
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) out.push([xs[i], xs[j]])
  return out
}
function overlap(a, b) {
  const e = 0.01
  return a.x < b.x + b.w - e && b.x < a.x + a.w - e && a.y < b.y + b.h - e && b.y < a.y + a.h - e
}
function push(m, k, v) { (m.get(k) ?? m.set(k, []).get(k)).push(v) }

console.log('check ok — 넓이 비례·겹침 없음·부모 안 들어감·지연 가르기·깨지는 것 되짚기')
