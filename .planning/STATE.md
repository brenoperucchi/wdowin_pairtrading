# Project State

## Project Reference

See: [`STATARB_2026_KNOWLEDGE.md`](../STATARB_2026_KNOWLEDGE.md), [`docs/MAPA_GERAL_DO_PROJETO.md`](../docs/MAPA_GERAL_DO_PROJETO.md), [`docs/PLANO_COMERCIAL_SAAS_MAGICWALLS.md`](../docs/PLANO_COMERCIAL_SAAS_MAGICWALLS.md) & [`.planning/PROJECT.md`](PROJECT.md). Documento de estado atualizado em **22/11/2026**.

**Core value:** Ecossistema quantitativo completo para `WIN` e `WDO` na B3 combinando: (1) cálculo diário GEX/Walls (`gex/`), (2) execução automatizada no MetaTrader 5 com a carteira **Top 10 EAs** na XP (`2004051`), (3) cockpit analítico local em `127.0.0.1:8080` + painéis Vite `5174` / `5176` / `5178`, e (4) plataforma SaaS **MagicWalls** (`app.magicwalls.com.br` + `api.magicwalls.com.br`).
**Current focus:** Operação live da carteira **Top 10 MT5** com Monitor v4.20 (`Stop G 950 / W 400 / D 0` + push ligado) e reconciliação diária (`scripts/reconcile_mt5_vs_bt.py`), paper trading no painel `5176` (`ESP_DIV_V22_WIN` + Carteira V3.2) e operação/estabilização do SaaS MagicWalls em produção.

## Current Position

Status: **Em Produção (Stack Local + Túnel Cloudflare + SaaS Cloud + MT5 Top 10 XP `2004051`)**
Last activity: **22/11/2026** — Consolidação operacional da infraestrutura, segurança e governança:

1. **Backend & Painéis Locais (supervisionados por `keep_dashboards_alive.py` / tarefa `JumbaDashboardsWatchdog`):**
   - **Backend FastAPI (`server.py`):** `http://127.0.0.1:8080` (bind restrito a `127.0.0.1`, `/health` assíncrono não-bloqueante, `/api/flow/inject-history` travado por padrão e sem semente aleatória de fluxo).
   - **Frontends Vite locais:** `5174` (Robôs MT5 / Carteiras), `5176` (Sniper Divergência `ESP_DIV_V22_WIN` + Carteira V3.2), `5178` (Gráfico Diário Manual WIN/WDO).
   - **Proxies públicos somente-leitura (`scripts/painel_publico.py`):** `127.0.0.1:5199` (modo `5178`) e `127.0.0.1:5198` (modo `5176`), expostos via `cloudflared` nomeado `magicwalls` (`config/cloudflared-magicwalls.yml` -> `walls.css-pro.com.br` e `roboswalls.css-pro.com.br`).
2. **Plataforma SaaS MagicWalls (`cloud_saas/`):**
   - **Frontend Edge (Cloudflare Pages):** `https://app.magicwalls.com.br` (build `regime-dashboard/build-saas.mjs` -> `dist-saas/`).
   - **Cloud API (Railway):** `https://api.magicwalls.com.br` (`cloud_saas/app.py`, FastAPI + JWT/entitlements server-side + sessões únicas).
   - **Dados & Cache:** **Supabase** (6 tabelas com RLS: `profiles`, `subscriptions`, `active_sessions`, `terms_acceptance`, `audit_logs`, `producer_heartbeats`) + **Upstash Redis** (sessões ativas e snapshots `core`/`pro`).
   - **Produtor Push (`scripts/cloud_publisher.py`):** lê `127.0.0.1:8080`, sanitiza payloads `core`/`pro`, assina via HMAC-SHA256 e publica na Cloud API; supervisionado automaticamente pelo watchdog `keep_dashboards_alive.py` (`--role primary --producer-id pc-local-01`).
3. **Carteira MT5 Live (XP `2004051`):**
   - Migração em **19/11/2026** para a carteira **Top 10 (`Campeões + EST-09/10`)**: 7 robôs WIN (`88004, 88007, 88009, 88010, 88013, 88014, 88015`) + 3 robôs WDO (`89001, 89005, 89007`).
   - Fonte única canônica no repositório em `mt5/Experts/Jumba_GEX_NWE/` (duplicatas da raiz `mt5/Experts/Jumba_*` removidas).
   - **`Jumba_Portfolio_Live_Monitor.mq5` v4.20:** Stop Diário configurado em **`Global R$ 950 / WIN R$ 400 / WDO R$ 0`** e `InpSendPushOnStop = true` (requer compilação F7 no MetaEditor do terminal para atualizar `.ex5` em produção).
   - Reconciliação diária Live vs Backtest disponível via `scripts/reconcile_mt5_vs_bt.py`.
4. **Paper Trading (`5176`):**
   - **`ESP_DIV_V22_WIN`** (`core/especialista_v22.py`, motor de divergência v3.2) + **Carteira V3.2** (`core/carteira_v32_estrategias.py`: `C1a_BRK_WIN`, `V1a_DIV_WDO`, `SYM_DIV_WIN`, `SYM_DIV_WDO`) operando em **paper trading**.
   - **Execução Python -> MT5:** não existe `core/mt5_executor.py` nem chamadas `mt5.order_send()` no backend Python; toda execução live ocorre diretamente pelos Expert Advisors MQL5 no MetaTrader 5.

## Key Decisions (Consolidated 22/11/2026)

- **Watchdog Nativo (`keep_dashboards_alive.py`) substitui PM2 (`ecosystem.config.js`):** supervisão única via tarefa `JumbaDashboardsWatchdog` com rotação de logs, período de carência de startup na porta `8080` e supervisão de `cloud_publisher.py`.
- **Fonte Única Canônica de EAs Jumba:** todos os fontes `.mq5` e binários `.ex5` `Jumba_*` no repositório residem exclusivamente em `mt5/Experts/Jumba_GEX_NWE/` (`mt5/build_and_compile_mt5_eas.py` atualizado para não duplicar na raiz).
- **Stop Diário Oficial em Produção (Top 10):** `InpMaxDailyLossGlobal = 950.0`, `InpMaxDailyLossWin = 400.0`, `InpMaxDailyLossWdo = 0.0`, com `InpSendPushOnStop = true` no Monitor v4.20.
- **Sinais Sem Repintura:** barras M5 fechadas têm seus sinais congelados no histórico e regras de `ESP_DIV_V22_WIN` / Carteira V3.2 compartilham implementação causal única entre histórico e ao vivo.
- **Blindagem MT5:** toda comunicação Python com a DLL do MetaTrader 5 permanece serializada em thread única (`_single_mt5_executor` + `_mt5_lock`), exclusivamente para leitura de cotações/histórico/posições (zero envio de ordens pelo backend).
