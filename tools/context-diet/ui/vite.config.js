import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import fs from 'node:fs'
import path from 'node:path'

const DATA = path.resolve(import.meta.dirname, '../data')
const FIXTURE = path.resolve(import.meta.dirname, 'fixtures/decisions.sample.json')

// ../data/*.json을 읽어 주고, 결정 상태를 ../data/decisions-state.json에 쓴다.
// decisions.json이 아직 없으면 fixture를 같은 자리에서 내보낸다 — 화면은 한 경로만 안다.
// ponytail: dev 서버 미들웨어 하나. 별도 백엔드는 화면이 요구할 때.
function dataApi() {
  return {
    name: 'context-diet-data',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url || '').split('?')[0]

        if (req.method === 'GET' && /^\/data\/[\w.-]+\.json$/.test(url)) {
          let file = path.join(DATA, path.basename(url))
          if (url === '/data/decisions.json' && !fs.existsSync(file)) file = FIXTURE
          if (!fs.existsSync(file)) { res.statusCode = 404; return res.end('{}') }
          res.setHeader('content-type', 'application/json')
          return res.end(fs.readFileSync(file))
        }

        if (req.method === 'POST' && url === '/api/decision') {
          let body = ''
          req.on('data', (c) => { body += c; if (body.length > 2e5) req.destroy() })
          req.on('end', () => {
            let item
            try { item = JSON.parse(body) } catch { res.statusCode = 400; return res.end('{"error":"bad json"}') }
            const { id, choice, memo, message } = item || {}
            const ok = ['keep', 'remove', 'shrink', 'hold', null, undefined]
            const okChoice = ok.includes(choice) || /^merge:[\w.+-]+$/.test(choice ?? '')
            if (!id || !okChoice) {
              res.statusCode = 400
              return res.end('{"error":"id, choice(keep|remove|shrink|hold|merge:<이름>|null) required"}')
            }
            const file = path.join(DATA, 'decisions-state.json')
            let doc = {}
            if (fs.existsSync(file)) {
              try { doc = JSON.parse(fs.readFileSync(file, 'utf8')) } catch { doc = {} }
            }
            const prev = doc[id] ?? { choice: null, memo: '', thread: [] }
            const at = new Date().toISOString()
            const thread = Array.isArray(prev.thread) ? [...prev.thread] : []
            if (typeof message === 'string' && message.trim()) thread.push({ by: 'user', at, text: message.trim() })
            doc[id] = {
              choice: choice === undefined ? prev.choice : choice,
              memo: memo === undefined ? prev.memo : memo,
              updated_at: at,
              thread,
            }
            fs.writeFileSync(file, JSON.stringify(doc, null, 2) + '\n')
            res.setHeader('content-type', 'application/json')
            res.end(JSON.stringify({ ok: true, id, updated_at: at }))
          })
          return
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [svelte(), dataApi()],
  server: { host: '127.0.0.1', strictPort: false },
})
