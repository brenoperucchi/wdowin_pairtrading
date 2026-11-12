import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Config temporaria para apresentacao via tunel (nao commitar)
const rewriteApi = {
  name: 'tunnel-rewrite-api',
  enforce: 'pre',
  transform(code, id) {
    if (id.includes('node_modules') || !/\.(jsx?|tsx?)$/.test(id.split('?')[0])) return null
    if (!/(localhost|127\.0\.0\.1):8080/.test(code)) return null
    return { code: code.replace(/https?:\/\/(localhost|127\.0\.0\.1):8080/g, ''), map: null }
  },
}
export default defineConfig({
  plugins: [rewriteApi, react()],
  server: {
    host: '127.0.0.1', port: 5177, strictPort: true, allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080', changeOrigin: true,
        bypass(req, res) {
          if (req.method !== 'GET' && req.method !== 'HEAD' && req.method !== 'OPTIONS') {
            res.statusCode = 405; res.end('read-only'); return false
          }
        },
      },
    },
  },
})
