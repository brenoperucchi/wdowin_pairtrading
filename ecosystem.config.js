/*
 * OBSOLETO / APOSENTADO (22/11/2026)
 * ---------------------------------------------------------------------------
 * Este arquivo de configuracao do PM2 nao e mais utilizado em producao.
 * Toda a orquestracao e supervisao dos servicos locais foi migrada para:
 *   - Watchdog Python: keep_dashboards_alive.py
 *   - Tarefa Agendada do Windows: Magic WallsDashboardsWatchdog
 *
 * Servicos hoje supervisionados pelo watchdog:
 *   - FastAPI (server.py em 127.0.0.1:8080)
 *   - Frontends Vite (5174, 5176, 5178)
 *   - Proxies publicos somente-leitura (scripts/painel_publico.py em 5198 e 5199)
 *   - Tunel Cloudflare nomeado magicwalls (config/cloudflared-magicwalls.yml)
 *   - Produtor Push Cloud SaaS (scripts/cloud_publisher.py)
 *
 * Mantido apenas para referencia historica. Nao iniciar via `pm2 start`.
 */
module.exports = {
  apps: [
    {
      name: 'wdo-backend',
      script: 'server.py',
      interpreter: 'python',
      watch: false
    },
    {
      name: 'wdo-frontend',
      script: './node_modules/vite/bin/vite.js',
      cwd: './regime-dashboard',
      watch: false,
      env: {
        NODE_ENV: 'development'
      }
    }
  ]
};
