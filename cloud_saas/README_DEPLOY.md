# Deploy em Produção — Arquitetura Push SaaS MagicWalls (`@magicwallsb3`)

## Visão Geral (Zero SPOF no PC Local)
- **Persistência (Supabase PostgreSQL / PostgREST):** 6 tabelas (`profiles`, `subscriptions`, `active_sessions`, `terms_acceptance`, `audit_logs`, `producer_heartbeats`) definidas em [supabase_schema.sql](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/supabase_schema.sql), com Row Level Security habilitado e acesso exclusivo via `SUPABASE_SERVICE_ROLE_KEY`.
- **Cache Edge (Upstash Redis REST):** sessões únicas (`sess:{user_id}` -> `401 SESSION_REPLACED`) e snapshots `core` / `pro` em memória.
- **Cloud API (Railway ou Fly.io `gru`):** container [Dockerfile](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/Dockerfile) (FastAPI + PostgREST `httpx`, sem dependências compiladas C).
- **Frontend (Cloudflare Pages):** build estático via `cd regime-dashboard && node build-saas.mjs` (`dist-saas/`).
- **Produtor Push ([cloud_publisher.py](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/scripts/cloud_publisher.py)):**
  - **Fase 1 (0–40 clientes):** PC local com nobreak + 4G/5G failover (`--role primary`).
  - **Fase 2 (40+ clientes):** VPS Windows dedicada (`--role primary`) + PC local em Hot Standby (`--role standby`).

---

## Passo 1 — Banco Supabase (6+2 Tabelas + RLS)
1. Crie um projeto no Supabase (região América do Sul / São Paulo quando disponível).
2. Abra **SQL Editor** e execute integralmente [supabase_schema.sql](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/supabase_schema.sql) (em instalações novas) ou a migração incremental idempotente [002_trial_activation.sql](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/migrations/002_trial_activation.sql) (para ativação de trials de 15 dias, convites e lista de espera).
3. Em **Project Settings -> API**, copie:
   - `SUPABASE_URL` (`https://<ref>.supabase.co`)
   - `SUPABASE_SERVICE_ROLE_KEY` (nunca use no frontend; nunca versione em Git; nunca use `serviceAccountKey.json`).

### Variáveis do Ambiente de Trials (15 dias)
- `MW_TRIAL_MODE=open` (`open` | `invite_only` | `paused`)
- `MW_TRIAL_DAYS=15`
- `MW_TRIAL_MAX_ACTIVE=50` (`0` = sem teto)
- `MW_TRIAL_MAX_PER_IP_24H=3` e `MW_TRIAL_MAX_PER_FP_30D=2`
- `MW_TURNSTILE_SITE_KEY` e `MW_TURNSTILE_SECRET_KEY` (Cloudflare Turnstile anti-bot; opcional)

---

## Passo 2 — Upstash Redis REST
1. Crie um database Redis na Upstash (preferencialmente `sa-east-1`).
2. Copie **REST URL** (`UPSTASH_REDIS_REST_URL`) e **REST Token** (`UPSTASH_REDIS_REST_TOKEN`).

---

## Passo 3 — Deploy da Cloud API (Railway ou Fly.io)

### Opção A — Railway ([railway.toml](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/railway.toml))
1. Conecte o repositório na Railway mantendo a **Root Directory** na raiz (`/`) e configure o Config File para `cloud_saas/railway.toml` (ou copie as variáveis de [cloud_saas/.env.example](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/.env.example)).
2. Defina todas as secrets (`MW_JWT_SECRET`, `MW_PUSH_HMAC_SECRET`, `MW_ADMIN_API_KEY`, `MW_BILLING_WEBHOOK_SECRET`, `MW_MT5_LICENSE_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `MW_CORS_ORIGINS`).
3. Após o deploy, confirme `GET https://<seu-dominio>/health` retornando `"db_backend": "supabase"` e `"store_backend": "upstash_redis"`.

### Opção B — Fly.io São Paulo `gru` ([fly.toml](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/cloud_saas/fly.toml))
Na raiz do repositório:
```powershell
fly launch --no-deploy -c cloud_saas/fly.toml --dockerfile cloud_saas/Dockerfile
fly secrets set `
  MW_JWT_SECRET="<secret>" `
  MW_PUSH_HMAC_SECRET="<secret>" `
  MW_ADMIN_API_KEY="<secret>" `
  MW_BILLING_WEBHOOK_SECRET="<secret>" `
  MW_MT5_LICENSE_SECRET="<secret>" `
  SUPABASE_URL="https://<ref>.supabase.co" `
  SUPABASE_SERVICE_ROLE_KEY="<service-role-key>" `
  UPSTASH_REDIS_REST_URL="https://<endpoint>.upstash.io" `
  UPSTASH_REDIS_REST_TOKEN="<token>" `
  MW_CORS_ORIGINS="https://www.magicwalls.com.br"
fly deploy -c cloud_saas/fly.toml --dockerfile cloud_saas/Dockerfile
```

---

## Passo 4 — Frontend Cloudflare Pages, Verificação & Produtor Push

### 4.1 Frontend (`dist-saas/`)
Configure no Cloudflare Pages:
- **Root directory:** `regime-dashboard`
- **Build command:** `node build-saas.mjs`
- **Build output directory:** `dist-saas`
- **Environment variables:**
  - `VITE_API_BASE=https://api.magicwalls.com.br`
  - `VITE_SAAS_AUTH=1`
  - `VITE_FORCE_WALLS_FLOW=1`

### 4.2 Verificador Automático de Conexões Cloud
Com as variáveis preenchidas no shell (sem gravar segredos em disco):
```powershell
.\.venv\Scripts\python.exe scripts\verify_cloud_connections.py --require-all
```
O script valida sem alterar dados reais:
1. Acesso PostgREST às **6 tabelas** do Supabase (`profiles`, `subscriptions`, `active_sessions`, `terms_acceptance`, `audit_logs`, `producer_heartbeats`).
2. Roundtrip `SET` -> `GET` -> `DEL` no Upstash Redis.
3. Saúde da Cloud API (`GET /health` e `GET /api/v1/feed/status`).

### 4.3 Ligar Produtor Push Local / VPS
```powershell
$env:MW_CLOUD_API_URL = "https://api.magicwalls.com.br"
$env:MW_PUSH_HMAC_SECRET = "<mesmo-segredo-da-nuvem>"
$env:TELEGRAM_BOT_TOKEN = "<bot-token>"
$env:TELEGRAM_CHAT_ID = "<seu-chat-id>"

# Primário (VPS ou PC principal)
.\.venv\Scripts\python.exe scripts\cloud_publisher.py --role primary --producer-id vps-sp-01

# Hot Standby (PC backup)
.\.venv\Scripts\python.exe scripts\cloud_publisher.py --role standby --producer-id pc-local-backup
```
